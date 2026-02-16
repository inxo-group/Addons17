# l10n_do_accounting/models/res_partner.py
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

try:
    from stdnum.do import rnc, cedula  # noqa
except (ImportError, IOError) as err:
    _logger.debug(str(err))


class Partner(models.Model):
    _inherit = "res.partner"

    sale_fiscal_type_id = fields.Many2one(
        comodel_name="account.fiscal.type",
        string="Sale Fiscal Type",
        domain=[("type", "=", "out_invoice")],
        compute="_compute_sale_fiscal_type_id",
        inverse="_inverse_sale_fiscal_type_id",
        index=True,
        store=True,
    )

    purchase_fiscal_type_id = fields.Many2one(
        "account.fiscal.type",
        string="Purchase Fiscal Type",
        domain=[("type", "=", "in_invoice")],
    )

    expense_type = fields.Selection(
        [
            ("01", "01 - Gastos de Personal"),
            ("02", "02 - Gastos por Trabajo, Suministros y Servicios"),
            ("03", "03 - Arrendamientos"),
            ("04", "04 - Gastos de Activos Fijos"),
            ("05", "05 - Gastos de Representación"),
            ("06", "06 - Otras Deducciones Admitidas"),
            ("07", "07 - Gastos Financieros"),
            ("08", "08 - Gastos Extraordinarios"),
            ("09", "09 - Compras y Gastos que forman parte del Costo de Venta"),
            ("10", "10 - Adquisiciones de Activos"),
            ("11", "11 - Gastos de Seguro"),
        ],
        string="Expense Type",
    )

    is_fiscal_info_required = fields.Boolean(compute="_compute_is_fiscal_info_required", store=False)

    country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country",
        ondelete="restrict",
        default=lambda self: self.env.ref("base.do"),
    )

    
    l10n_do_country_code = fields.Char(
        related="country_id.code",
        store=True,
        readonly=True,
    )

    @api.depends("sale_fiscal_type_id")
    def _compute_is_fiscal_info_required(self):
        for rec in self:
            rec.is_fiscal_info_required = bool(rec.sale_fiscal_type_id.prefix in ["B01", "B14", "B15"])

    def _get_fiscal_type_domain(self, prefix):
        return self.env["account.fiscal.type"].search(
            [("type", "=", "out_invoice"), ("prefix", "=", prefix)], limit=1
        )

    @api.depends("vat", "country_id", "name", "parent_id", "parent_id.sale_fiscal_type_id")
    def _compute_sale_fiscal_type_id(self):
        do_country = self.env.ref("base.do")
        for partner in self:
            vat = partner.name if partner.name and partner.name.isdigit() else partner.vat
            is_do = bool(partner.country_id == do_country)
            new_fiscal_type = partner.sale_fiscal_type_id

            if not is_do:
                new_fiscal_type = self._get_fiscal_type_domain("B16")
            elif partner.parent_id:
                new_fiscal_type = partner.parent_id.sale_fiscal_type_id
            elif vat and not (partner.name and partner.name.isdigit()) and not partner.sale_fiscal_type_id:
                if vat.isdigit() and len(vat) == 9:
                    if partner.name and "MINISTERIO" in partner.name:
                        new_fiscal_type = self._get_fiscal_type_domain("B15")
                    elif partner.name and any(n for n in ("IGLESIA", "ZONA FRANCA") if n in partner.name):
                        new_fiscal_type = self._get_fiscal_type_domain("B14")
                    else:
                        new_fiscal_type = self._get_fiscal_type_domain("B01")
                else:
                    new_fiscal_type = self._get_fiscal_type_domain("B02")
            elif is_do and not partner.sale_fiscal_type_id:
                new_fiscal_type = self._get_fiscal_type_domain("B02")

            partner.sale_fiscal_type_id = new_fiscal_type

            # NO escribir aquí property_account_position_id (evita write dentro de compute)

    def _inverse_sale_fiscal_type_id(self):
        for partner in self:
            ft = partner.sale_fiscal_type_id
            if ft and ft.fiscal_position_id:
                partner.property_account_position_id = ft.fiscal_position_id

    @api.model
    def get_sale_fiscal_type_id_selection(self):
        return {
            "sale_fiscal_type_id": self.sale_fiscal_type_id.id,
            "sale_fiscal_type_list": [
                {"id": "final", "name": "Consumo", "ticket_label": "Consumo", "is_default": True},
                {"id": "fiscal", "name": "Crédito Fiscal"},
                {"id": "gov", "name": "Gubernamental"},
                {"id": "special", "name": "Regímenes Especiales"},
                {"id": "unico", "name": "Único Ingreso"},
                {"id": "export", "name": "Exportaciones"},
            ],
            "sale_fiscal_type_vat": {
                "rnc": ["fiscal", "gov", "special"],
                "ced": ["final", "fiscal"],
                "other": ["final"],
                "no_vat": ["final", "unico", "export"],
            },
        }
