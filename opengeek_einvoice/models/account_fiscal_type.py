from odoo import fields, models


class AccountFiscalType(models.Model):
    _inherit = "account.fiscal.type"

    is_electronic_sequence = fields.Boolean(
        string="Secuencia Electrónica",
        help="Indica si este tipo fiscal usa secuencia electrónica.",
        copy=False,
    )
