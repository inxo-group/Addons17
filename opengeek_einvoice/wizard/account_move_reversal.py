# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    credit_note_reason = fields.Selection(
        [
            ("1", "Anula el NCF modificado"),
            ("2", "Corrige Texto del Comprobante Fiscal modificado"),
            ("3", "Corrige montos del NCF modificado"),
            ("4", "Reemplazo NCF emitido en contingencia"),
            ("5", "Referencia Factura Consumo Electrónica"),
        ],
        string="Tipo de Nota de Crédito",
        required=False,
    )

    @api.constrains("credit_note_reason")
    def _check_credit_note_reason_required(self):
        for wiz in self:
            move_ids = wiz.move_ids
            if not move_ids:
                continue
            needs_reason = any(m.move_type in ("out_invoice", "in_invoice") for m in move_ids)
            if needs_reason and not wiz.credit_note_reason:
                raise UserError("Debe seleccionar el Tipo de Nota de Crédito (DGII).")

    def _prepare_default_reversal(self, move):
        res = super()._prepare_default_reversal(move)
        if self.credit_note_reason:
            res["credit_note_reason"] = self.credit_note_reason
        if "reason" in self._fields:
            res["credit_reason"] = self.reason
        return res
