# -*- coding: utf-8 -*-
from odoo import fields, models


class UomUom(models.Model):
    _inherit = "uom.uom"

    code = fields.Integer(
        string="Code",
        copy=False,
        index=True,
        help="Código DGII de la unidad de medida.",
    )
