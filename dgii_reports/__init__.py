from odoo import api, SUPERUSER_ID

from . import models
from . import wizard


def update_taxes(env):
    env = api.Environment(env.cr, SUPERUSER_ID, dict(env.context))

    IrModelData = env["ir.model.data"]
    Tax = env["account.tax"]

    tax_data = IrModelData.search([
        ("model", "=", "account.tax"),
        ("module", "=", "l10n_do"),
    ])

    taxes = Tax.browse(tax_data.mapped("res_id")).exists()
    if not taxes:
        return

    xmlid_map = {
        "tax_18_sale": {"l10n_do_tax_type": "itbis"},
        "tax_18_sale_incl": {"l10n_do_tax_type": "itbis"},
        "tax_18_purch": {"l10n_do_tax_type": "itbis"},
        "tax_18_purch_incl": {"l10n_do_tax_type": "itbis"},
        "tax_16_purch": {"l10n_do_tax_type": "itbis"},
        "tax_16_purch_incl": {"l10n_do_tax_type": "itbis"},
        "tax_9_purch": {"l10n_do_tax_type": "itbis"},
        "tax_9_purch_incl": {"l10n_do_tax_type": "itbis"},
        "tax_8_purch": {"l10n_do_tax_type": "itbis"},
        "tax_8_purch_incl": {"l10n_do_tax_type": "itbis"},
        "tax_18_purch_serv": {"l10n_do_tax_type": "itbis"},
        "tax_18_purch_serv_incl": {"l10n_do_tax_type": "itbis"},
        "tax_18_importation": {"l10n_do_tax_type": "itbis"},
        "tax_18_of_10": {"l10n_do_tax_type": "itbis"},
        "tax_18_10_total_mount": {"l10n_do_tax_type": "itbis"},
        "tax_18_property_cost": {"l10n_do_tax_type": "itbis"},
        "tax_18_serv_cost": {"l10n_do_tax_type": "itbis"},

        "tax_tip_sale": {"l10n_do_tax_type": "tip"},
        "tax_tip_purch": {"l10n_do_tax_type": "tip"},

        "tax_10_telco": {"l10n_do_tax_type": "isc"},
        "tax_2_telco": {"l10n_do_tax_type": "other"},
        "tax_0015_bank": {"l10n_do_tax_type": "other"},

        "ret_10_income_rent": {"l10n_do_tax_type": "isr", "isr_retention_type": "01"},
        "ret_10_income_person": {"l10n_do_tax_type": "isr", "isr_retention_type": "02"},
        "ret_10_income_dividend": {"l10n_do_tax_type": "isr", "isr_retention_type": "03"},
        "ret_2_income_person": {"l10n_do_tax_type": "isr", "isr_retention_type": "03"},
        "ret_2_income_transfer": {"l10n_do_tax_type": "isr", "isr_retention_type": "03"},
        "ret_27_income_remittance": {"l10n_do_tax_type": "isr", "isr_retention_type": "03"},
        "ret_5_income_gov": {"l10n_do_tax_type": "isr", "isr_retention_type": "07"},

        "ret_100_tax_person": {"l10n_do_tax_type": "ritbis"},
        "ret_100_tax_security": {"l10n_do_tax_type": "ritbis"},
        "ret_100_tax_nonprofit": {"l10n_do_tax_type": "ritbis"},
        "ret_30_tax_moral": {"l10n_do_tax_type": "ritbis"},
        "ret_75_tax_nonformal": {"l10n_do_tax_type": "ritbis"},
    }

    name_to_tax = {}
    data_by_res_id = {d.res_id: d.name for d in tax_data}
    for tax in taxes:
        xml_name = data_by_res_id.get(tax.id)
        if xml_name:
            name_to_tax[xml_name] = tax

    for xml_name, vals in xmlid_map.items():
        tax = name_to_tax.get(xml_name)
        if not tax:
            continue
        write_vals = {}
        if getattr(tax, "l10n_do_tax_type", False) in (False, "none"):
            write_vals["l10n_do_tax_type"] = vals["l10n_do_tax_type"]
        if "isr_retention_type" in vals and not getattr(tax, "isr_retention_type", False):
            write_vals["isr_retention_type"] = vals["isr_retention_type"]
        if write_vals:
            tax.write(write_vals)

    remaining = taxes.filtered(lambda t: getattr(t, "l10n_do_tax_type", "none") in (False, "none"))
    for tax in remaining:
        name = (tax.name or "").lower()
        group = (tax.tax_group_id.name or "").lower() if tax.tax_group_id else ""

        if "itbis" in name or "itbis" in group:
            tax.write({"l10n_do_tax_type": "itbis"})
        elif "propina" in name or "tip" in name or "propina" in group:
            tax.write({"l10n_do_tax_type": "tip"})
        elif "isc" in name or "selectivo" in name or "isc" in group or "selectivo" in group:
            tax.write({"l10n_do_tax_type": "isc"})
        elif "isr" in name or "renta" in name or "isr" in group:
            tax.write({"l10n_do_tax_type": "isr"})
        elif "ret" in name and "itbis" in name:
            tax.write({"l10n_do_tax_type": "ritbis"})
        else:
            tax.write({"l10n_do_tax_type": "other"})
