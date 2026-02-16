# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    e_expiration_token = fields.Datetime(
        string="Expiration Token",
        readonly=True,
        copy=False,
        help="Expiration date of the token used to connect with the e-invoice service.",
    )

    e_token_client = fields.Char(
        string="Token Client",
        readonly=True,
        copy=False,
        help="Access token used to connect with the e-invoice service.",
    )

    e_username = fields.Char(
        string="Username",
        copy=False,
        help="Username used to connect with the e-invoice service.",
    )

    e_password = fields.Char(
        string="Password",
        copy=False,
        groups="base.group_system",
        help="Password used to connect with the e-invoice service.",
    )
