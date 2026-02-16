from odoo import models, fields

class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_do_country_code = fields.Char(
        related="country_id.code",
        store=True,
        readonly=True,
    )
