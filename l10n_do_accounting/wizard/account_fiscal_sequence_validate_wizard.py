# l10n_do_accounting/wizard/account_fiscal_sequence_validate_wizard.py
from odoo import models, fields, _
from odoo.exceptions import ValidationError


class AccountFiscalSequenceValidateWizard(models.TransientModel):
    _name = "account.fiscal.sequence.validate_wizard"
    _description = "Account Fiscal Sequence Validate Wizard"

    name = fields.Char()
    fiscal_sequence_id = fields.Many2one("account.fiscal.sequence", string="Fiscal sequence")

    def confirm_cancel(self):
        self.ensure_one()
        if not self.fiscal_sequence_id:
            raise ValidationError(_("There is no Fiscal Sequence to perform this action."))

        action = (self._context or {}).get("action", False)
        if action == "confirm":
            self.fiscal_sequence_id._action_confirm()
        elif action == "cancel":
            self.fiscal_sequence_id._action_cancel()
