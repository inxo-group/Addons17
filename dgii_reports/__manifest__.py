
{
    "name": "Declaraciones DGII",
    "summary": """
        Este módulo extiende las funcionalidades del l10n_do_accounting,
        integrando los reportes de declaraciones fiscales
    """,
    "author": "OpenGeeksLab",
    "license": "LGPL-3",
    "category": "Accounting",
    "version": "17.0.1.0.0",
    "depends": [
        "web",
        "account",
        "l10n_do",
        "l10n_do_accounting",
    ],
    "external_dependencies": {
        "python": ["pycountry"],
    },
    "data": [
        "data/invoice_service_type_detail_data.xml",
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "views/res_partner_views.xml",
        "views/account_account_views.xml",
        "views/account_invoice_views.xml",
        "views/dgii_report_views.xml",
        "views/account_tax_views.xml",
        "wizard/dgii_report_regenerate_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dgii_reports/static/src/scss/dgii_reports.scss",
            "dgii_reports/static/src/js/widget.js",
        ],
    },
    "post_init_hook": "update_taxes",
    "installable": True,
    "application": False,
}
