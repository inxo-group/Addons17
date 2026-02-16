from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    related = fields.Selection(
        selection=[('0', 'Not Related'), ('1', 'Related')],
        default='0',
        string='Related Party',
    )
