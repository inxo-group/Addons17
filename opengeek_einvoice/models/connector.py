# -*- coding: utf-8 -*-
from odoo import fields, models


class EInvoiceConnector(models.Model):
    _name = "opengeek.einvoice"
    _description = "OpenGeek E-Invoice Connector"
    _rec_name = "name"

    name = fields.Char(
        string="Proveedor",
        default="Open Geeks Lab, SRL",
        readonly=True,
        required=True,
    )
