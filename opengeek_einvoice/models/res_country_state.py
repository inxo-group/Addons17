# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCountryStateInherit(models.Model):
    _inherit = "res.country.state"

    code_do = fields.Char(string="Code DO")
