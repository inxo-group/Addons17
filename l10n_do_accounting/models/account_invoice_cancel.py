# l10n_do_accounting/models/account_invoice_cancel.py
from odoo import models, fields, _
from odoo.exceptions import UserError


class AccountInvoiceCancel(models.TransientModel):
    _name = "account.invoice.cancel"
    _description = "Cancel the Selected Invoice"

    annulation_type = fields.Selection(
        [
            ("01", "01 - Deterioro de Factura Pre-impresa"),
            ("02", "02 - Errores de Impresión (Factura Pre-impresa)"),
            ("03", "03 - Impresión Defectuosa"),
            ("04", "04 - Corrección de la Información"),
            ("05", "05 - Cambio de Productos"),
            ("06", "06 - Devolución de Productos"),
            ("07", "07 - Omisión de Productos"),
            ("08", "08 - Errores en Secuencia de NCF"),
            ("09", "09 - Por Cese de Operaciones"),
            ("10", "10 - Pérdida o Hurto de Talonarios"),
        ],
        required=True,
        default=lambda self: self._context.get("annulation_type", "04"),
    )

    def invoice_cancel(self):
        active_ids = (self._context or {}).get("active_ids", []) or []
        moves = self.env["account.move"].browse(active_ids)

        for move in moves:
            if move.state == "cancel" or move.payment_state in ("paid", "in_payment"):
                raise UserError(
                    _(
                        "Selected invoice(s) cannot be cancelled as they are "
                        "already in 'Cancelled' or 'Paid' state."
                    )
                )

            move.annulation_type = self.annulation_type
            move.with_context(l10n_do_force_cancel=True).button_cancel()

        return {"type": "ir.actions.act_window_close"}
