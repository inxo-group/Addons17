from werkzeug.utils import redirect

from odoo.http import Controller, request, route


class DgiiReportsControllers(Controller):

    @route(["/dgii_reports/<string:ncf_rnc>"], type="http", auth="user", website=False)
    def redirect_link(self, ncf_rnc):
        env = request.env
        base_url = env["ir.config_parameter"].sudo().get_param("web.base.url")

        ncf_rnc = (ncf_rnc or "").strip()

        if ncf_rnc[:1] == "B":
            move = env["account.move"].search([("ref", "=", ncf_rnc)], limit=1)
            if not move:
                return redirect(base_url)

            action_xmlid_by_move_type = {
                "out_invoice": "account.action_move_out_invoice_type",
                "in_invoice": "account.action_move_in_invoice_type",
                "out_refund": "account.action_move_out_refund_type",
                "in_refund": "account.action_move_in_refund_type",
            }

            xmlid = action_xmlid_by_move_type.get(move.move_type)
            if not xmlid:
                return redirect(base_url)

            action = env["ir.actions.act_window"]._for_xml_id(xmlid)

            url = (
                f"{base_url}/web#"
                f"id={move.id}&action={action['id']}&model=account.move&view_type=form"
            )
            return redirect(url)

        partner = env["res.partner"].search([("vat", "=", ncf_rnc)], limit=1)
        if not partner:
            return redirect(base_url)

        url = f"{base_url}/web#id={partner.id}&model=res.partner&view_type=form"
        return redirect(url)
