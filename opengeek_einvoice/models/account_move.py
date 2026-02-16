# -*- coding: utf-8 -*-
import base64
import json
import logging
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

import qrcode

from odoo import fields, models
from odoo.exceptions import UserError

from ..service.webservice import OpenGeekEInvoiceService

_logger = logging.getLogger(__name__)

D = Decimal

_FE_ALERT_RECIPIENTS = [
    "elopez@opengeekslab.com.do",
    "jlora@opengeekslab.com.do",
]


class AccountMove(models.Model):
    _inherit = "account.move"

    einvoice_status = fields.Char(string="Estatus DGII", readonly=True)
    einvoice_trackId = fields.Char(string="Track Id", readonly=True)
    dgii_qr_image = fields.Binary(string="QR DGII", attachment=True)
    dgii_codigo_seguridad = fields.Char(
        string="Código de Seguridad", readonly=True, help="Código de seguridad del QR"
    )
    dgii_fecha_firma = fields.Datetime(string="Fecha de Firma DGII")
    credit_reason = fields.Char(
        string="Motivo de Crédito", readonly=True, help="Motivo de la nota de crédito"
    )
    credit_note_reason = fields.Selection(
        [
            ("1", "1: Anula el NCF modificado"),
            ("2", "2: Corrige Texto del Comprobante Fiscal modificado"),
            ("3", "3: Corrige montos del NCF modificado"),
            ("4", "4: Reemplazo NCF emitido en contingencia"),
            ("5", "5: Referencia Factura Consumo Electrónica.81"),
        ],
        string="Tipo de Nota de Crédito DGII",
    )
    debit_note_reason = fields.Selection(
        [
            ("2", "Corrige Texto del Comprobante Fiscal modificado"),
            ("3", "Corrige montos del NCF modificado"),
            ("4", "Reemplazo NCF emitido en contingencia"),
            ("5", "Referencia Factura Consumo Electrónica.81"),
        ],
        string="Tipo de Nota de Débito",
    )
    debit_reason = fields.Char(string="Motivo Nota de Débito")

    currency_rate = fields.Float(string="Tipo de Cambio")
    esubmitted = fields.Boolean(string="eInvoice Submitted")
    payload_send_dgii = fields.Text(string="eInvoice Payload JSON", readonly=True)
    exception_message_dgii = fields.Text(string="eInvoice Exception Message", readonly=True)

    def copy(self, default=None):
        default = dict(default or {})
        default.update(
            {
                "einvoice_status": False,
                "einvoice_trackId": False,
                "dgii_qr_image": False,
                "dgii_codigo_seguridad": False,
                "dgii_fecha_firma": False,
                "currency_rate": False,
                "esubmitted": False,
                "payload_send_dgii": False,
                "exception_message_dgii": False,
            }
        )
        return super().copy(default)

    def e_send_invoice(self):
        for move in self:
            move.generate_complete_einvoice_json()

    def handle_einvoice_response(self, response):
        """Procesa la respuesta del webservice de DGII y genera el QR."""
        try:
            if isinstance(response, str):
                try:
                    response_data = json.loads(response)
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": "La respuesta no es un JSON válido",
                        "raw_response": response,
                    }
            elif isinstance(response, dict):
                response_data = response
            else:
                return {
                    "success": False,
                    "error": f"Tipo de respuesta no soportado: {type(response)}",
                    "raw_response": str(response),
                }

            errores = []
            mensajes = response_data.get("mensajes", [])
            if isinstance(mensajes, list):
                for mensaje in mensajes:
                    if isinstance(mensaje, dict):
                        errores.append(
                            {
                                "message": mensaje.get("valor", ""),
                                "code": mensaje.get("codigo", "UNKNOWN"),
                            }
                        )

            qr_base64_bytes = None
            qr_url = response_data.get("QR")
            if qr_url:
                qr_img = qrcode.make(qr_url)
                buffer = BytesIO()
                qr_img.save(buffer, format="PNG")
                qr_base64_bytes = base64.b64encode(buffer.getvalue())  # bytes (OK for Binary)

            return {
                "success": response_data.get("estado") in ("Aceptado", "Aceptado Condicional", "Rechazado"),
                "status": response_data.get("estado"),
                "trackId": response_data.get("trackId"),
                "code": response_data.get("codigo"),
                "message": errores[0]["message"] if errores else "",
                "errors": errores,
                "qr_url": qr_url,
                "qr_image_base64": qr_base64_bytes,
                "codigo_seguridad": response_data.get("CodigoSeguridad"),
                "fecha_firma": response_data.get("FechaHoraFirma"),
                "raw_response": response_data,
            }

        except Exception as e:
            _logger.exception("FE: error procesando respuesta DGII")
            return {
                "success": False,
                "error": f"Error inesperado al procesar la respuesta: {str(e)}",
                "raw_response": response if isinstance(response, dict) else str(response),
            }

    def generate_complete_einvoice_json(self):
        self.ensure_one()
        account_move = self

        def clean_dict(d):
            """Elimina None/'' y listas vacías; NO elimina ceros."""
            if isinstance(d, dict):
                cleaned = {
                    k: clean_dict(v)
                    for k, v in d.items()
                    if v is not None and (not isinstance(v, str) or v != "")
                }
                return cleaned if cleaned else None
            if isinstance(d, list):
                lst = [clean_dict(v) for v in d]
                return [it for it in lst if it is not None]
            return d

        def s_money(x, places="0.01", keep_zero=True):
            """Redondea y formatea a string; si keep_zero=False oculta 0."""
            if x is None or (isinstance(x, str) and x == ""):
                return None
            q = D(str(x)).quantize(D(places), rounding=ROUND_HALF_UP)
            if q == 0 and not keep_zero:
                return None
            return str(q)

        def _line_is_i1(line):
            has_itbis18 = any(
                getattr(t, "l10n_do_tax_type", "") == "itbis"
                and float(getattr(t, "amount", 0.0)) == 18.0
                for t in line.tax_ids
            )
            has_ritbis_nonzero = any(
                getattr(t, "l10n_do_tax_type", "") == "ritbis"
                and abs(float(getattr(t, "amount", 0.0))) > 0.0
                for t in line.tax_ids
            )
            return has_itbis18 or has_ritbis_nonzero

        def _line_is_i2(line):
            return any(
                getattr(t, "l10n_do_tax_type", "") == "itbis"
                and float(getattr(t, "amount", 0.0)) == 16.0
                for t in line.tax_ids
            )

        def _line_is_i3(line):
            has_itbis0 = any(
                getattr(t, "l10n_do_tax_type", "") == "itbis"
                and float(getattr(t, "amount", 0.0)) == 0.0
                for t in line.tax_ids
            )
            has_ritbis0 = any(
                getattr(t, "l10n_do_tax_type", "") == "ritbis"
                and float(getattr(t, "amount", 0.0)) == 0.0
                for t in line.tax_ids
            )
            return has_itbis0 or has_ritbis0

        def fmt_ritbis_ret(ritbis_total, currency_rate, has_itbis3_line=False):
            if not ritbis_total:
                return "0.00" if has_itbis3_line else None
            amt = abs(D(str(ritbis_total)))
            if currency_rate:
                amt *= D(str(currency_rate))
            amt = amt.quantize(D("0.01"), rounding=ROUND_HALF_UP)
            if amt == 0 and not has_itbis3_line:
                return None
            return str(amt)

        def fmt_isr_ret(isr_total, currency_rate):
            if not isr_total:
                return None
            amt = abs(D(str(isr_total)))
            if currency_rate:
                amt *= D(str(currency_rate))
            amt = amt.quantize(D("0.01"), rounding=ROUND_HALF_UP)
            return None if amt == 0 else str(amt)

        def _is_isc_for_itbis(tax_rec):
            code = (
                (getattr(tax_rec, "dgii_code", None) or getattr(tax_rec, "l10n_do_code", None) or "")
                .strip()
            )
            if code.isdigit():
                return 6 <= int(code) <= 39
            return getattr(tax_rec, "l10n_do_tax_type", "") == "isc"

        if not account_move.fiscal_type_id.is_electronic_sequence:
            raise UserError(
                "El tipo fiscal de la factura no es electrónico. "
                "Por favor, verifique el tipo fiscal de la factura."
            )

        after_30_days = False
        is_credit_note = account_move.move_type == "out_refund"
        is_debit_note = bool(getattr(account_move, "is_debit_note", False)) and account_move.move_type in (
            "out_invoice",
            "in_invoice",
        )

        if is_credit_note or is_debit_note:
            original_move = self.env["account.move"].search(
                [
                    ("ref", "=", getattr(account_move, "origin_out", False)),
                    ("state", "=", "posted"),
                    ("company_id", "=", account_move.company_id.id),
                ],
                limit=1,
            )

            if is_credit_note:
                fecha_mod_dt = (
                    (account_move.reversed_entry_id and account_move.reversed_entry_id.invoice_date)
                    or (original_move and original_move.invoice_date)
                )
            else:
                fecha_mod_dt = original_move and original_move.invoice_date

            fecha_mod = fecha_mod_dt.strftime("%d-%m-%Y") if fecha_mod_dt else ""

            codigo_mod = account_move.credit_note_reason if is_credit_note else account_move.debit_note_reason
            razon_mod = account_move.credit_reason if is_credit_note else account_move.debit_reason

            einvoice_reference = {
                "NCFModificado": getattr(account_move, "origin_out", "") or "",
                "FechaNCFModificado": fecha_mod,
                "CodigoModificacion": codigo_mod or "1",
                "RazonModificacion": razon_mod or "Anula el NCF modificado",
            }

            if original_move and original_move.invoice_date and account_move.invoice_date:
                days_diff = (account_move.invoice_date - original_move.invoice_date).days
                after_30_days = days_diff > 30

        if account_move.currency_id != account_move.company_id.currency_id:
            currency_rate = round(
                account_move.currency_id._get_conversion_rate(
                    from_currency=account_move.currency_id,
                    to_currency=account_move.company_id.currency_id,
                    company=account_move.company_id,
                    date=account_move.invoice_date,
                ),
                2,
            )
            account_move.currency_rate = currency_rate
        else:
            currency_rate = None

        def _to_company(amount):
            return round(float(amount) * currency_rate, 2) if currency_rate else float(amount)

        todas_exentas = all(
            any("Exento" in (tax.name or "") for tax in line.tax_ids)
            for line in account_move.invoice_line_ids
        )

        monto_exento = sum(
            line.price_subtotal
            for line in account_move.invoice_line_ids
            if any("Exento" in (tax.name or "") for tax in line.tax_ids)
        )
        monto_exento = round(monto_exento * currency_rate, 2) if currency_rate else monto_exento

        if todas_exentas:
            monto_gravado_global = 0.00
        else:
            if currency_rate and monto_exento:
                monto_gravado_global = round(float(account_move.amount_untaxed * currency_rate) - monto_exento, 2)
            elif currency_rate and not monto_exento:
                monto_gravado_global = round(float(account_move.amount_untaxed) * currency_rate, 2)
            elif not currency_rate and monto_exento:
                monto_gravado_global = round(float(account_move.amount_untaxed - monto_exento), 2)
            else:
                monto_gravado_global = float(account_move.amount_untaxed)

        if monto_gravado_global < 0:
            monto_gravado_global *= -1

        base_i1 = sum(_to_company(l.price_subtotal) for l in account_move.invoice_line_ids if _line_is_i1(l))
        base_i2 = sum(_to_company(l.price_subtotal) for l in account_move.invoice_line_ids if _line_is_i2(l))
        base_i3 = sum(_to_company(l.price_subtotal) for l in account_move.invoice_line_ids if _line_is_i3(l))

        isc_i1 = 0.0
        isc_i2 = 0.0
        for line in account_move.invoice_line_ids:
            if not line.tax_ids:
                continue
            taxes_res = line.tax_ids.compute_all(
                line.price_unit,
                currency=account_move.currency_id,
                quantity=line.quantity,
                product=line.product_id,
                partner=account_move.partner_id,
            )
            isc_line = 0.0
            for tdict in taxes_res.get("taxes", []):
                tax_rec = self.env["account.tax"].browse(tdict["id"])
                if _is_isc_for_itbis(tax_rec):
                    isc_line += tdict["amount"]
            isc_line_company = _to_company(isc_line)
            if _line_is_i1(line):
                isc_i1 += isc_line_company
            elif _line_is_i2(line):
                isc_i2 += isc_line_company

        ITBIS1_RATE = D("0.18")
        ITBIS2_RATE = D("0.16")

        b1 = D(str(base_i1 or 0))
        b2 = D(str(base_i2 or 0))
        b3 = D(str(base_i3 or 0))
        exento = D(str(monto_exento or 0))

        b1_for_tax = b1 + D(str(isc_i1))
        b2_for_tax = b2 + D(str(isc_i2))

        t1 = (b1_for_tax * ITBIS1_RATE).quantize(D("0.01"), rounding=ROUND_HALF_UP) if b1_for_tax > 0 else D("0.00")
        t2 = (b2_for_tax * ITBIS2_RATE).quantize(D("0.01"), rounding=ROUND_HALF_UP) if b2_for_tax > 0 else D("0.00")
        t3 = D("0.00")

        total_itbis = (t1 + t2 + t3).quantize(D("0.01"), rounding=ROUND_HALF_UP)
        monto_gravado_total = b1 + b2 + b3
        monto_total = (monto_gravado_total + total_itbis + exento).quantize(D("0.1"), rounding=ROUND_HALF_UP)

        has_i1 = b1 > 0
        has_i2 = b2 > 0
        has_i3 = b3 > 0
        has_any_gravado = has_i1 or has_i2 or has_i3

        # IMPORTANTE: se mantiene _get_tax_line_ids() porque proviene de dgii_reports
        withholding_itbis = 0.0
        income_withholding = 0.0
        tax_line_ids = account_move._get_tax_line_ids()
        if tax_line_ids:
            withholding_itbis = abs(
                sum(
                    tl.balance
                    for tl in tax_line_ids
                    if getattr(tl.tax_line_id, "l10n_do_tax_type", "") == "ritbis"
                )
            )
            income_withholding = abs(
                sum(
                    tl.balance
                    for tl in tax_line_ids
                    if getattr(tl.tax_line_id, "l10n_do_tax_type", "") == "isr"
                )
            )

        tipo_ecf = (getattr(account_move.fiscal_type_id, "prefix", "") or "").lstrip("E")

        monto_total_dec = D(str(monto_total or 0))
        if tipo_ecf == "32" and monto_total_dec < D("250000"):
            tipo_pago = "1" if account_move.amount_residual == 0 else "3"
        else:
            tipo_pago = "1" if account_move.amount_residual == 0 else ("2" if account_move.amount_residual > 0 else "3")

        if (
            account_move.invoice_date_due
            and account_move.amount_residual > 0
            and not (tipo_ecf == "32" and monto_total_dec < D("250000"))
        ):
            fecha_limite_pago = account_move.invoice_date_due.strftime("%d-%m-%Y")
        else:
            fecha_limite_pago = None

        formapago = "7" if account_move.move_type in ["out_refund", "in_refund"] else "4"

        vat_raw = (account_move.partner_id.vat or "").strip()
        vat_digits = re.sub(r"\D", "", vat_raw)

        rnc_comprador = vat_digits if vat_digits and len(vat_digits) in (9, 11) else None
        id_extranjero = None if rnc_comprador else (vat_raw or None)

        isr_withholding_total = 0.0
        ritbis_withholding_total = 0.0

        indicador_agente = "1" if (tipo_ecf == "41" or isr_withholding_total or withholding_itbis) else None

        einvoice = {
            "Encabezado": {
                "TipoeCF": tipo_ecf or None,
                "eNCF": account_move.ref or None,
                "FechaVencimientoSecuencia": (
                    account_move.ncf_expiration_date.strftime("%d-%m-%Y")
                    if account_move.ncf_expiration_date
                    else (
                        account_move.fiscal_sequence_id.expiration_date.strftime("%d-%m-%Y")
                        if account_move.fiscal_sequence_id and account_move.fiscal_sequence_id.expiration_date
                        else None
                    )
                ),
                "IndicadorNotaCredito": (
                    "1" if (account_move.move_type == "out_refund" and after_30_days)
                    else ("0" if account_move.move_type == "out_refund" and not after_30_days else None)
                ),
                "IndicadorMontoGravado": "0",
                "TipoIngresos": getattr(account_move, "income_type", None) or None,
                "TipoPago": tipo_pago,
                "FechaLimitePago": fecha_limite_pago,
                "NumeroFacturaInterna": account_move.name or None,
                "NumeroPedidoInterno": account_move.name or None,
                "FormasDePago": [
                    {
                        "FormaPago": formapago,
                        "MontoPago": (str(account_move.amount_total) if account_move.move_type == "out_invoice" else "0.00"),
                    },
                ],
            },
            "Emisor": {
                "RNCEmisor": account_move.company_id.vat or None,
                "RazonSocialEmisor": account_move.company_id.name or None,
                "NombreComercial": account_move.company_id.name or None,
                "DireccionEmisor": ", ".join(
                    filter(None, [account_move.company_id.street, account_move.company_id.street2, account_move.company_id.city])
                )
                or None,
                "FechaEmision": (account_move.invoice_date.strftime("%d-%m-%Y") if account_move.invoice_date else None),
            },
            "Comprador": {
                "RNCComprador": rnc_comprador,
                "IdentificadorExtranjero": id_extranjero,
                "RazonSocialComprador": account_move.partner_id.name or None,
                "ContactoComprador": " | ".join(filter(None, [account_move.partner_id.name, account_move.partner_id.phone])) or None,
                "CorreoComprador": account_move.partner_id.email or None,
                "DireccionComprador": ", ".join(
                    filter(None, [account_move.partner_id.street, account_move.partner_id.street2, account_move.partner_id.city])
                )
                or None,
                "codigoProvinciaComprador": getattr(account_move.partner_id.state_id, "code_do", None),
                "fechaEntrega": (account_move.invoice_date_due.strftime("%d-%m-%Y") if account_move.invoice_date_due else None),
            },
            "Totales": clean_dict(
                {
                    "MontoGravadoTotal": s_money(monto_gravado_total, places="0.01", keep_zero=False) if has_any_gravado else None,
                    "MontoGravadoI1": s_money(b1, keep_zero=False) if has_i1 else None,
                    "MontoGravadoI2": s_money(b2, keep_zero=False) if has_i2 else None,
                    "MontoGravadoI3": s_money(b3, keep_zero=False) if has_i3 else None,
                    "MontoExento": s_money(exento, keep_zero=False) if exento > 0 else None,
                    "ITBIS1": "18" if has_i1 else None,
                    "ITBIS2": "16" if has_i2 else None,
                    "ITBIS3": "0" if has_i3 else None,
                    "TotalITBIS": s_money(total_itbis, keep_zero=True) if (t1 > 0 or t2 > 0 or has_i3) else None,
                    "TotalITBIS1": s_money(t1, keep_zero=False) if has_i1 else None,
                    "TotalITBIS2": s_money(t2, keep_zero=False) if has_i2 else None,
                    "TotalITBIS3": "0.00" if has_i3 else None,
                    "TotalITBISRetenido": (
                        str(withholding_itbis)
                        if withholding_itbis
                        else ("0.00" if indicador_agente else ("0.00" if (not withholding_itbis and income_withholding) else None))
                    ),
                    "TotalISRRetencion": (str(income_withholding) if income_withholding else None),
                    "MontoTotal": s_money(monto_total, places="0.1", keep_zero=True),
                }
            ),
            "Items": [],
        }

        if currency_rate:
            total_itbis_otra_moneda = float(t1 + t2 + t3) / float(currency_rate)
            otra_moneda = {
                "TipoMoneda": account_move.currency_id.name,
                "TipoCambio": str(round(float(currency_rate), 2)),
                "MontoGravadoTotalOtraMoneda": (
                    str(round(float((b1 + b2 + b3) / D(str(currency_rate))), 2)) if (b1 > 0 or b2 > 0 or b3 > 0) else None
                ),
                "MontoGravado1OtraMoneda": (str(round(float(b1 / D(str(currency_rate))), 2)) if b1 > 0 else None),
                "MontoGravado2OtraMoneda": (str(round(float(b2 / D(str(currency_rate))), 2)) if b2 > 0 else None),
                "MontoGravado3OtraMoneda": (str(round(float(b3 / D(str(currency_rate))), 2)) if b3 > 0 else None),
                "MontoExentoOtraMoneda": (str(round(float(exento / D(str(currency_rate))), 2)) if exento > 0 else None),
                "TotalITBIS1OtraMoneda": (str(round(float(t1) / float(currency_rate), 2)) if t1 > 0 else None),
                "TotalITBIS2OtraMoneda": (str(round(float(t2) / float(currency_rate), 2)) if t2 > 0 else None),
                "TotalITBIS3OtraMoneda": ("0.00" if has_i3 else None),
                "TotalITBISOtraMoneda": (
                    str(round(total_itbis_otra_moneda, 2))
                    if (t1 != 0 or t2 != 0 or t3 != 0)
                    else ("0.00" if has_i3 else None)
                ),
                "MontoTotalOtraMoneda": (
                    str(round(float((b1 + b2 + b3 + exento + (t1 + t2 + t3))) / float(currency_rate), 2))
                    if (b1 > 0 or b2 > 0 or b3 > 0 or exento > 0 or (t1 + t2 + t3) > 0)
                    else None
                ),
            }
            otra_moneda_clean = clean_dict(otra_moneda)
            if otra_moneda_clean:
                einvoice["OtraMoneda"] = otra_moneda_clean

        company = account_move.company_id

        lines = 1
        for line in account_move.invoice_line_ids:
            if line.price_subtotal == 0 or not line.tax_ids:
                continue

            if line.currency_id != company.currency_id:
                amount_other_currency = line.currency_id._convert(
                    line.price_subtotal,
                    company.currency_id,
                    company,
                    account_move.invoice_date or fields.Date.today(),
                )

                taxes_included = line.tax_ids.filtered(lambda t: t.price_include)
                if taxes_included:
                    tax_result = line.tax_ids.compute_all(
                        line.price_unit,
                        currency=line.currency_id,
                        quantity=line.quantity,
                        product=line.product_id,
                        partner=account_move.partner_id,
                    )
                    base_unit_price = tax_result["total_excluded"] / (line.quantity or 1.0)
                else:
                    base_unit_price = line.price_unit

                item_currency_unit_price = line.currency_id._convert(
                    base_unit_price,
                    company.currency_id,
                    company,
                    account_move.invoice_date or fields.Date.today(),
                )
            else:
                amount_other_currency = None
                item_currency_unit_price = None
                base_unit_price = line.price_unit

            taxes_res = (
                line.tax_ids.compute_all(
                    line.price_unit,
                    currency=account_move.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=account_move.partner_id,
                )
                if line.tax_ids
                else {"taxes": []}
            )

            isr_withholding_total = 0.0
            ritbis_withholding_total = 0.0
            for tdict in taxes_res.get("taxes", []):
                tax_record = self.env["account.tax"].browse(tdict["id"])
                kind = getattr(tax_record, "l10n_do_tax_type", "")
                if kind == "isr":
                    isr_withholding_total += tdict["amount"]
                elif kind == "ritbis":
                    ritbis_withholding_total += tdict["amount"]

            has_itbis3_line = _line_is_i3(line)

            first_tax = line.tax_ids[:1]
            price_include_flag = bool(first_tax and first_tax[0].price_include)

            item = {
                "NumeroLinea": str(lines),
                "IndicadorFacturacion": (
                    str(line.tax_ids[0].etax) if (line.tax_ids and getattr(line.tax_ids[0], "etax", False)) else "3"
                ),
                "IndicadorAgenteRetencionoPercepcion": indicador_agente,
                "MontoITBISRetenido": fmt_ritbis_ret(ritbis_withholding_total, currency_rate, has_itbis3_line),
                "MontoISRRetenido": fmt_isr_ret(isr_withholding_total, currency_rate),
                "NombreItem": line.product_id.name or line.name or None,
                "IndicadorBienoServicio": ("2" if line.product_id.type == "service" else "1"),
                "CantidadItem": str(float(line.quantity)) if line.quantity else "0.0",
                "UnidadMedida": str(line.product_uom_id.code) if getattr(line.product_uom_id, "code", False) else None,
                "PrecioUnitarioItem": (
                    str(round(float(item_currency_unit_price), 2))
                    if item_currency_unit_price is not None
                    else str(round(float(line.price_unit), 2))
                ),
                "MontoItem": (
                    "0.00"
                    if (account_move.move_type == "out_invoice" and account_move.credit_note_reason == "2")
                    else (
                        str(round(float(amount_other_currency), 2))
                        if amount_other_currency is not None
                        else str(round(float(line.price_subtotal), 2))
                    )
                ),
            }

            if currency_rate:
                otra_det = {
                    "PrecioOtraMoneda": (str(round(float(base_unit_price), 2)) if item_currency_unit_price is not None else None),
                    "MontoItemOtraMoneda": (
                        str(round(float(line.price_subtotal), 2))
                        if (amount_other_currency is not None and not price_include_flag)
                        else (
                            str(round(float(line.price_unit * line.quantity), 2))
                            if (amount_other_currency is not None and price_include_flag)
                            else None
                        )
                    ),
                }
                otra_det_clean = clean_dict(otra_det)
                if otra_det_clean:
                    item["OtraMonedaDetalle"] = otra_det_clean

            einvoice["Items"].append(item)
            lines += 1

        if is_credit_note or is_debit_note:
            einvoice["InformacionReferencia"] = einvoice_reference

        otra_moneda = einvoice.get("OtraMoneda")
        if otra_moneda:
            non_null_values = {k: v for k, v in otra_moneda.items() if v not in (None, "0", "0.0", "0.00")}
            if not non_null_values:
                einvoice.pop("OtraMoneda", None)
        else:
            einvoice.pop("OtraMoneda", None)

        einvoice_clean = clean_dict(einvoice) or {}
        einvoice_json = json.dumps(einvoice_clean, ensure_ascii=False, separators=(",", ":"))

        response = OpenGeekEInvoiceService.einvoice_request(einvoice_json, account_move.company_id)
        result = self.handle_einvoice_response(response)

        fecha_firma_str = result.get("fecha_firma")
        fecha_firma_dt = None
        if fecha_firma_str:
            for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M"):
                try:
                    fecha_firma_dt = datetime.strptime(fecha_firma_str, fmt)
                    break
                except ValueError:
                    continue

        if not result.get("success"):
            errors = result.get("errors") or result.get("error") or "Error al procesar la factura electrónica"
            errors_str = json.dumps(errors, ensure_ascii=False) if not isinstance(errors, str) else errors

            payload_str = einvoice_json
            if not isinstance(payload_str, str):
                payload_str = json.dumps(payload_str, ensure_ascii=False)

            vals = {
                "esubmitted": True,
                "einvoice_status": result.get("status"),
                "einvoice_trackId": result.get("trackId"),
                "dgii_qr_image": result.get("qr_image_base64"),
                "dgii_codigo_seguridad": result.get("codigo_seguridad"),
                "dgii_fecha_firma": fecha_firma_dt,
                "payload_send_dgii": payload_str,
                "exception_message_dgii": errors_str or (result.get("message") or "Error"),
            }
            account_move.write(vals)

            account_move._notify_fe_exception(payload=einvoice_json)

            raise UserError(errors_str)

        payload_str = einvoice_json if isinstance(einvoice_json, str) else json.dumps(einvoice_json, ensure_ascii=False)
        account_move.write({
            "esubmitted": True,
            "einvoice_status": result.get("status") or "Aceptado",
            "einvoice_trackId": result.get("trackId"),
            "dgii_qr_image": result.get("qr_image_base64"),
            "dgii_codigo_seguridad": result.get("codigo_seguridad"),
            "dgii_fecha_firma": fecha_firma_dt,
            "payload_send_dgii": payload_str,
            "exception_message_dgii": None,
        })

    def _notify_fe_exception(self, payload):
        self.ensure_one()

        try:
            pretty_obj = json.loads(payload or "{}")
            pretty = json.dumps(pretty_obj, ensure_ascii=False, indent=2)
            raw_bytes = pretty.encode("utf-8")
        except Exception:
            pretty = str(payload or "")
            raw_bytes = pretty.encode("utf-8")

        attachment_ids = []
        try:
            att = self.env["ir.attachment"].create(
                {
                    "name": f"payload_{self.name or self.id}.json",
                    "type": "binary",
                    "datas": base64.b64encode(raw_bytes),
                    "res_model": self._name,
                    "res_id": self.id,
                    "mimetype": "application/json",
                }
            )
            attachment_ids = [att.id]
        except Exception:
            _logger.exception("FE: error creando adjunto del payload")

        template = self.env.ref("opengeek_einvoice.mail_template_fe_exception_dgii", raise_if_not_found=False)
        if not template:
            return False

        try:
            for email in _FE_ALERT_RECIPIENTS:
                email_values = {
                    "email_to": email,
                    "attachment_ids": [(6, 0, attachment_ids)] if attachment_ids else [],
                }
                template.send_mail(self.id, force_send=True, email_values=email_values)
            return True
        except Exception:
            _logger.exception("FE: error enviando notificación por plantilla")
            return False