# l10n_do_accounting/wizard/account_invoice_refund.py
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    refund_method = fields.Selection(selection="_get_refund_method_selection", default="refund", required=True)
    is_vendor_refund = fields.Boolean(string="Vendor refund")
    refund_ref = fields.Char(string="NCF")
    ncf_expiration_date = fields.Date(string="Valid until")
    is_fiscal_refund = fields.Boolean(string="Fiscal refund")

    @api.model
    def default_get(self, field_list):
        res = super().default_get(field_list)
        invoice_ids = self.env["account.move"].browse((self._context or {}).get("active_ids", []))
        res.update(
            {
                "is_fiscal_refund": set(invoice_ids.mapped("is_l10n_do_fiscal_invoice")) == {True},
                "is_vendor_refund": set(invoice_ids.mapped("move_type")) == {"in_invoice"},
            }
        )
        return res

    @api.model
    def _get_refund_method_selection(self):
        if self._context.get("debit_note", False):
            return [
                ("refund", "Partial Debit note"),
                ("cancel", "Full Debit note"),
            ]
        return [
            ("refund", "Partial Refund"),
            ("cancel", "Full Refund"),
            ("modify", "Full refund and new draft invoice"),
        ]

    def reverse_moves(self):
        self.ensure_one()
        if self.refund_ref and self.is_fiscal_refund:
            self.env["account.fiscal.type"].check_format_fiscal_number(self.refund_ref, "in_refund")
        return super().reverse_moves()

    def _prepare_default_reversal(self, move):
        res = super()._prepare_default_reversal(move)
        if self.is_fiscal_refund:
            res.update(
                {
                    "ref": self.refund_ref,
                    "origin_out": move.ref,
                    "expense_type": move.expense_type,
                    "income_type": move.income_type,
                    "ncf_expiration_date": self.ncf_expiration_date,
                    "fiscal_type_id": False,
                }
            )
        return res
