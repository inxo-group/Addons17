# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountDebitNoteWizard(models.TransientModel):
    _name = "account.debit.note.wizard"
    _description = "Create Debit Note from Posted Invoice/Bill"

    dgii_debit_note_reason = fields.Selection(
        [
            ("2", "Corrige Texto del Comprobante Fiscal modificado"),
            ("3", "Corrige montos del NCF modificado"),
            ("4", "Reemplazo NCF emitido en contingencia"),
            ("5", "Referencia Factura Consumo Electrónica"),
        ],
        required=True,
        string="Tipo de Nota de Débito",
    )

    date = fields.Date(
        string="Debit Note Date",
        default=lambda self: fields.Date.context_today(self),
        required=True,
    )
    reason = fields.Char(string="Reason", required=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="Use Specific Journal",
        domain="[('company_id','=',company_id), ('type','in',['sale','purchase'])]",
    )
    copy_lines = fields.Boolean(string="Copy Original Lines", default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company
    )

    @api.model
    def _get_active_moves(self):
        moves = self.env["account.move"].browse(self._context.get("active_ids", []))
        moves = moves.filtered(lambda m: m.state == "posted" and m.move_type in ("out_invoice", "in_invoice"))
        if not moves:
            raise UserError("Seleccione al menos una factura *publicada* de cliente o proveedor.")
        return moves

    def action_create_debit_note(self):
        self.ensure_one()
        moves = self._get_active_moves()
        new_moves = self.env["account.move"]

        has_analytic_distribution = "analytic_distribution" in self.env["account.move.line"]._fields

        for src in moves:
            journal = self.journal_id or src.journal_id
            if not journal:
                raise UserError("Debe seleccionar un diario.")

            lines_to_copy = src.invoice_line_ids.filtered(lambda l: l.display_type in (False, "product"))

            line_cmds = []
            if self.copy_lines:
                for l in lines_to_copy:
                    vals = {
                        "name": l.name,
                        "product_id": l.product_id.id or False,
                        "quantity": l.quantity,
                        "price_unit": l.price_unit,
                        "discount": l.discount,
                        "tax_ids": [(6, 0, l.tax_ids.ids)],
                        "display_type": l.display_type,
                    }

                    if has_analytic_distribution and l.analytic_distribution:
                        vals["analytic_distribution"] = l.analytic_distribution
                    line_cmds.append((0, 0, vals))

            debit_vals = {
                "move_type": src.move_type,
                "company_id": src.company_id.id,
                "partner_id": src.partner_id.id,
                "currency_id": src.currency_id.id,
                "invoice_date": self.date,
                "journal_id": journal.id,
                "invoice_origin": src.name,
                "ref": "",
                "is_debit_note": True,
                "origin_out": src.ref,
                "debit_note_reason": self.dgii_debit_note_reason,
                "debit_reason": self.reason,
            }
            if line_cmds:
                debit_vals["invoice_line_ids"] = line_cmds

            ctx = {"default_move_type": src.move_type, "default_journal_id": journal.id}
            debit = self.env["account.move"].with_context(**ctx).create(debit_vals)

            if not debit.invoice_line_ids:
                tax_ids = src.invoice_line_ids[:1].tax_ids.ids if src.invoice_line_ids else []
                debit.write(
                    {
                        "invoice_line_ids": [
                            (0, 0, {"name": self.reason or "Debit note charge", "quantity": 1.0, "price_unit": 1.0, "tax_ids": [(6, 0, tax_ids)]})
                        ]
                    }
                )

            debit_map = {"out_invoice": "out_debit", "in_invoice": "in_debit"}
            target_type = debit_map.get(src.move_type)
            if not target_type:
                raise UserError("Tipo de movimiento no soportado para nota de débito.")

            ft = self.env["account.fiscal.type"].search([("type", "=", target_type)], limit=1)
            if not ft:
                raise UserError(f"Falta account.fiscal.type para {target_type} (ND).")
            debit.write({"fiscal_type_id": ft.id})

            if hasattr(debit, "_compute_fiscal_sequence"):
                debit._compute_fiscal_sequence()
            if hasattr(debit, "_recompute_dynamic_lines"):
                debit._recompute_dynamic_lines(recompute_all_taxes=True)

            if not getattr(debit.journal_id, "l10n_do_fiscal_journal", True):
                raise UserError("El diario seleccionado no es fiscal (l10n_do_fiscal_journal = False).")

            if (
                getattr(debit, "is_l10n_do_fiscal_invoice", False)
                and debit.fiscal_type_id
                and getattr(debit.fiscal_type_id, "assigned_sequence", False)
                and not getattr(debit, "fiscal_sequence_id", False)
            ):
                raise UserError("No hay Secuencia Fiscal activa para el tipo de Nota de Débito.")

            if debit.amount_total == 0:
                raise UserError("La Nota de Débito no tiene monto. Copia líneas o agrega conceptos.")

            debit.action_post()
            new_moves |= debit

        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_move_out_invoice_type")
        if len(new_moves) == 1:
            action.update({"res_id": new_moves.id, "views": [(False, "form")], "view_mode": "form"})
        else:
            action.update({"domain": [("id", "in", new_moves.ids)]})
        return action
