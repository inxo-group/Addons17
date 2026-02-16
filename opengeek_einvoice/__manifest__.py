# -*- coding: utf-8 -*-
{
    "name": "OpenGeek E-Invoice Connector",
    "summary": "DGII e-invoicing integration for Dominican Republic",
    "version": "17.0.1.0.0",
    "author": "OpenGeeksLab",
    "license": "LGPL-3",
    "category": "Accounting",
    "sequence": 10,
    "depends": [
        "base",
        "account",
        "l10n_do_accounting",
        "contacts",
        "stock",
        "uom",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",

        "wizard/account_move_reversal.xml",
        "wizard/account_debit_note_wizard_view.xml",

        "views/res_config_settings.xml",
        "views/account_move.xml",
        "views/account_tax.xml",
        "views/res_country_state.xml",
        "views/uom_uom.xml",
        "views/account_fiscal_type.xml",
        "views/product_template.xml",
        "views/account_move_debit_button_view.xml",

        "reports/einvoice_report.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
