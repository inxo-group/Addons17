# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplateInherit(models.Model):
    _inherit = "product.template"

    is_service_computed = fields.Integer(
        string="eIndicador",
        compute="_compute_is_service",
        store=True,
        copy=False,
        help="Indicador DGII: 2 = Servicio, 1 = Bien",
    )

    @api.depends("type")
    def _compute_is_service(self):
        for product in self:
            product.is_service_computed = 2 if product.type == "service" else 1
