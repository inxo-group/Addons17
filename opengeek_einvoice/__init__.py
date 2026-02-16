from odoo import api, SUPERUSER_ID

from . import models
from . import wizard


_CODE_DO_BY_STATE_CODE = {
    "01": "010000",
    "02": "020000",
    "03": "030000",
    "04": "040000",
    "05": "050000",
    "06": "060000",
    "07": "070000",
    "08": "080000",
    "09": "090000",
    "10": "100000",
    "11": "110000",
    "12": "120000",
    "13": "130000",
    "14": "140000",
    "15": "150000",
    "16": "160000",
    "17": "170000",
    "18": "180000",
    "19": "190000",
    "20": "200000",
    "21": "210000",
    "22": "220000",
    "23": "230000",
    "24": "240000",
    "25": "250000",
    "26": "260000",
    "27": "270000",
    "28": "280000",
    "29": "290000",
    "30": "300000",
    "31": "310000",
    "32": "320000",
}

_UOM_CODE_BY_XMLID = {
    "uom.product_uom_cm": "08",
    "uom.product_uom_day": "12",
    "uom.product_uom_unit": "43",
    "uom.product_uom_dozen": "13",
    "uom.product_uom_gal": "15",
    "uom.product_uom_gram": "17",
    "uom.product_uom_hour": "19",
    "uom.product_uom_kgm": "21",
    "uom.product_uom_lb": "23",
    "uom.product_uom_litre": "24",
    "uom.product_uom_meter": "26",
    "uom.uom_square_meter": "27",
    "uom.product_uom_cubic_meter": "28",
}

TEMPLATE_XMLID = "opengeek_einvoice.mail_template_fe_exception_dgii"

SUBJECT = "Notificación Error FE - Documento ${object.name or 'N/A'}"
EMAIL_FROM = "${object.company_id.email_formatted or user.email_formatted}"

BODY_HTML = """
<div>
  <p><strong>Se ha detectado una excepción durante el envío de la Factura Electrónica.</strong></p>

  <p><strong>Tipo de Documento:</strong> ${object.fiscal_type_id.name or 'No definido'}</p>
  <p><strong>Fecha/Hora:</strong> ${object.write_date or object.create_date}</p>
  <p><strong>Compañía:</strong> ${object.company_id.name or ''}</p>
  <p><strong>Cliente:</strong> ${object.partner_id.display_name or ''}</p>
  <p><strong>Factura:</strong> ${object.name or ''}</p>

  <p><strong>Mensaje de excepción:</strong><br/>${object.exception_message_dgii or 'Error desconocido'}</p>

  % if object.einvoice_status or object.einvoice_trackId:
    <p><strong>Estado / TrackId reportado por el conector:</strong>
      % if object.einvoice_status:
        Status: ${object.einvoice_status}
      % endif
      % if object.einvoice_trackId:
        | TrackId: ${object.einvoice_trackId}
      % endif
    </p>
  % endif

  <p><strong>Payload (resumen):</strong></p>
  <pre style="white-space:pre-wrap;word-wrap:break-word;">${object.payload_send_dgii or ''}</pre>
</div>
""".strip()


def post_init_hook(env):
    env = api.Environment(env.cr, SUPERUSER_ID, dict(env.context))

    do_country = env.ref("base.do", raise_if_not_found=False)
    if do_country:
        states = env["res.country.state"].search([("country_id", "=", do_country.id)])
        for st in states:
            code = (st.code or "").strip()
            code_do = _CODE_DO_BY_STATE_CODE.get(code)
            if code_do and st.code_do != code_do:
                st.code_do = code_do

    Tax = env["account.tax"]

    taxes_exempt = Tax.search([
        ("amount", "=", 0),
        ("amount_type", "=", "percent"),
        ("type_tax_use", "in", ("sale", "none", "purchase")),
    ])
    if taxes_exempt:
        taxes_exempt.write({"exent": True, "etax": 4})

    taxes_18 = Tax.search([
        ("amount", "=", 18),
        ("amount_type", "=", "percent"),
        ("type_tax_use", "in", ("sale", "none", "purchase")),
    ])
    if taxes_18:
        taxes_18.write({"etax": 1})

    taxes_16 = Tax.search([
        ("amount", "=", 16),
        ("amount_type", "=", "percent"),
        ("type_tax_use", "in", ("sale", "none", "purchase")),
    ])
    if taxes_16:
        taxes_16.write({"etax": 2})

    for xmlid, code in _UOM_CODE_BY_XMLID.items():
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec and rec._name == "uom.uom":
            if getattr(rec, "code", None) != code:
                rec.code = code

    model_move = env.ref("account.model_account_move")

    # buscar si ya existe por xmlid
    imd = env["ir.model.data"].sudo()
    existing = imd.search([
        ("module", "=", "opengeek_einvoice"),
        ("name", "=", "mail_template_fe_exception_dgii"),
    ], limit=1)

    vals = {
        "name": "Notificación Error FE: Excepción en Envío al DGII",
        "model_id": model_move.id,
        "subject": SUBJECT,
        "email_from": EMAIL_FROM,
        "body_html": BODY_HTML,
        "auto_delete": True,
    }

    if existing:
        template = env["mail.template"].sudo().browse(existing.res_id)
        if template.exists():
            template.write(vals)
            return

    template = env["mail.template"].sudo().create(vals)
    imd.create({
        "module": "opengeek_einvoice",
        "name": "mail_template_fe_exception_dgii",
        "model": "mail.template",
        "res_id": template.id,
        "noupdate": True,
    })
