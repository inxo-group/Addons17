# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    e_expiration_token = fields.Datetime(
        related="company_id.e_expiration_token",
        readonly=True,
        string="Token de Expiración",
        help="Expiration date of the token used to connect with the e-invoice service.",
    )
    e_username = fields.Char(
        related="company_id.e_username",
        readonly=False,
        string="Usuario",
    )
    e_password = fields.Char(
        related="company_id.e_password",
        readonly=False,
        string="Contraseña",
        password=True,
        groups="base.group_system",
    )

    # Toggle persistente por parámetro de sistema
    display_incoterm = fields.Boolean(
        string="Mostrar Incoterms",
        config_parameter="opengeek_einvoice.display_incoterm",
        help="Muestra campos/funcionalidad de Incoterms en el conector.",
    )
