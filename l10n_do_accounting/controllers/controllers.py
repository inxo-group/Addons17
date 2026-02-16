# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    from stdnum.do import rnc, cedula
except Exception as err:
    rnc = None
    cedula = None
    _logger.debug(str(err))


class Odoojs(http.Controller):

    @http.route(
        "/dgii_ws",
        auth="public",
        cors="*",
        type="http",
        methods=["GET"],
        csrf=False,
    )
    def index(self, **kwargs):
        term = (kwargs.get("term") or "").strip()

        query_dgii_wsmovil = request.env["ir.config_parameter"].sudo().get_param("dgii.wsmovil")
        if not term or query_dgii_wsmovil != "True":
            return request.make_response(
                json.dumps([]),
                headers=[("Content-Type", "application/json; charset=utf-8")],
            )

        if rnc is None:
            _logger.warning("python-stdnum not available; /dgii_ws disabled.")
            return request.make_response(
                json.dumps([]),
                headers=[("Content-Type", "application/json; charset=utf-8")],
            )

        try:
            if term.isdigit() and len(term) in (9, 11):
                result = rnc.check_dgii(term)
            else:
                result = rnc.search_dgii(term, end_at=20, start_at=1)
        except Exception as err:
            _logger.error("DGII lookup error: %s", err)
            result = None

        if result is None:
            payload = []
        else:
            if not isinstance(result, list):
                result = [result]

            for d in result:
                d["name"] = " ".join(re.split(r"\s+", d.get("name", ""), flags=re.UNICODE))
                d["label"] = "{} - {}".format(d.get("rnc", ""), d.get("name", ""))
            payload = result

        return request.make_response(
            json.dumps(payload),
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )

    @http.route(
        "/validate_rnc/",
        auth="public",
        cors="*",
        type="http",
        methods=["GET"],
        csrf=False,
    )
    def validate_rnc(self, **kwargs):
        """
        Check if the number provided is a valid RNC/Cédula.
        Params:
          rnc: string
        """
        num = (kwargs.get("rnc") or "").strip()

        if not num.isdigit():
            return request.make_response(
                json.dumps({"is_valid": False}),
                headers=[("Content-Type", "application/json; charset=utf-8")],
            )

        if rnc is None or cedula is None:
            _logger.warning("python-stdnum not available; /validate_rnc disabled.")
            return request.make_response(
                json.dumps({"is_valid": False, "info": None}),
                headers=[("Content-Type", "application/json; charset=utf-8")],
            )

        is_valid = (len(num) == 9 and rnc.is_valid(num)) or (len(num) == 11 and cedula.is_valid(num))
        if not is_valid:
            return request.make_response(
                json.dumps({"is_valid": False}),
                headers=[("Content-Type", "application/json; charset=utf-8")],
            )

        try:
            info = rnc.check_dgii(num)
        except Exception as err:
            info = None
            _logger.error("DGII check error: %s", err)

        if info is not None:
            info["name"] = " ".join(re.split(r"\s+", info.get("name", ""), flags=re.UNICODE))

        return request.make_response(
            json.dumps({"is_valid": True, "info": info}),
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )
