# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResPartnerInherit(models.Model):
    _inherit = "res.partner"

    @api.constrains("vat", "country_id")
    def _check_vat_numeric_only(self):
        """
        Para RD: el RNC/Cédula debe ser numérico.
        Para extranjeros: no se valida formato.
        """
        for partner in self:
            if (
                partner.vat
                and partner.country_id
                and partner.country_id.code == "DO"
                and not partner.vat.isdigit()
            ):
                raise ValidationError(
                    _(
                        "El RNC/Cédula solo puede contener números "
                        "para contribuyentes de República Dominicana."
                    )
                )
