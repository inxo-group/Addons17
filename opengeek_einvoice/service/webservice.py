# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta, timezone

import requests

_logger = logging.getLogger(__name__)


class OpenGeekEInvoiceService:
    AUTH_URL = "https://docs.opengeekslab.com.do/external/auth/iniciar-sesion"
    PROCESS_URL = "https://docs.opengeekslab.com.do/internal/einvoice_json/procesarjson/"

    AUTH_TIMEOUT = 30
    PROCESS_TIMEOUT = 60

    @classmethod
    def _utcnow(cls):
        return datetime.now(timezone.utc)

    @classmethod
    def _token_is_expired(cls, company):
        exp = company.e_expiration_token
        if not exp:
            return True
        exp_utc = exp.replace(tzinfo=timezone.utc)
        return cls._utcnow() >= exp_utc

    @classmethod
    def _authenticate(cls, company):
        if not company.e_username or not company.e_password:
            return {
                "success": False,
                "error": "Credenciales eInvoice no configuradas en la compañía.",
            }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {
            "username_email": company.e_username,
            "password": company.e_password,
        }

        try:
            resp = requests.post(cls.AUTH_URL, data=data, headers=headers, timeout=cls.AUTH_TIMEOUT)
        except requests.RequestException as e:
            _logger.exception("eInvoice AUTH: request error")
            return {
                "success": False,
                "error": f"Error de conexión autenticando eInvoice: {e}",
            }

        if resp.status_code != 200:
            _logger.error("eInvoice AUTH: status=%s body=%s", resp.status_code, resp.text)
            return {
                "success": False,
                "error": f"Error autenticando eInvoice ({resp.status_code})",
                "raw": resp.text,
            }

        try:
            auth_json = resp.json()
        except ValueError:
            return {
                "success": False,
                "error": "Respuesta de autenticación no es JSON válido.",
                "raw": resp.text,
            }

        data_json = auth_json.get("data") or {}
        token = data_json.get("accessToken")
        expires_in = data_json.get("expiresIn")

        if not token or not expires_in:
            return {
                "success": False,
                "error": "Respuesta de autenticación no contiene accessToken/expiresIn.",
                "raw": auth_json,
            }

        try:
            expires_in = int(expires_in)
        except Exception:
            return {
                "success": False,
                "error": "expiresIn inválido.",
                "raw": auth_json,
            }

        exp_dt_naive_utc = (cls._utcnow() + timedelta(seconds=expires_in)).replace(tzinfo=None)

        company.write(
            {
                "e_token_client": token,
                "e_expiration_token": exp_dt_naive_utc,
            }
        )

        return {"success": True, "token": token}

    @classmethod
    def einvoice_request(cls, json_data, company):
        _logger.info(json_data)
        token = company.e_token_client
        if not token or cls._token_is_expired(company):
            auth = cls._authenticate(company)
            if not auth.get("success"):
                return {"success": False, "error": auth.get("error"), "raw": auth.get("raw")}
            token = auth["token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = json_data
        if isinstance(payload, str):
            payload = json.loads(payload)

        def _do_request():
            return requests.post(
                cls.PROCESS_URL,
                json=payload,
                headers=headers,
                timeout=cls.PROCESS_TIMEOUT,
            )


        try:
            resp = _do_request()
            _logger.debug("eInvoice PROCESS: status=%s body=%s", resp.status_code, resp.text)
        except requests.RequestException as e:
            _logger.exception("eInvoice PROCESS: request error")
            return {"success": False, "error": f"Error de conexión procesando eInvoice: {e}"}

        if resp.status_code == 401:
            auth = cls._authenticate(company)
            if auth.get("success"):
                headers["Authorization"] = f"Bearer {auth['token']}"
                try:
                    resp = _do_request()
                except requests.RequestException as e:
                    _logger.exception("eInvoice PROCESS: retry request error")
                    return {"success": False, "error": f"Error de conexión reintentando eInvoice: {e}"}

        if resp.status_code >= 400:
            _logger.error("eInvoice PROCESS: status=%s body=%s", resp.status_code, resp.text)
            return {
                "success": False,
                "error": f"Error procesando eInvoice ({resp.status_code})",
                "raw": resp.text,
            }

        try:
            return resp.json()
        except ValueError:
            return {
                "success": False,
                "error": "Respuesta del servicio eInvoice no es JSON válido.",
                "raw": resp.text,
            }
