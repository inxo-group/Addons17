from odoo import fields, models


class AccountTaxInherit(models.Model):
    _inherit = "account.tax"

    etax = fields.Integer(
        string="eTax",
        help="Código interno usado por el conector para clasificar impuestos en el payload DGII.",
        copy=False,
        index=True,
    )
    exent = fields.Boolean(
        string="Exento",
        help="Marca el impuesto como exento para lógica de eInvoice.",
        copy=False,
        index=True,
    )
