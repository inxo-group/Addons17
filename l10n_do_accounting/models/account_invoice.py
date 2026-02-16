# l10n_do_accounting/models/account_invoice.py
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    from stdnum.do import ncf as ncf_validation  # noqa
except (ImportError, IOError) as err:
    _logger.debug(err)

ncf_dict = {
    "B01": "fiscal",
    "B02": "consumo",
    "B15": "gov",
    "B14": "especial",
    "B12": "unico",
    "B16": "export",
    "B03": "debit",
    "B04": "credit",
    "B13": "minor",
    "B11": "informal",
    "B17": "exterior",
}


class AccountInvoice(models.Model):
    _inherit = "account.move"

    fiscal_type_id = fields.Many2one(
        string="Fiscal type",
        comodel_name="account.fiscal.type",
        index=True,
    )
    available_fiscal_type_ids = fields.Many2many(
        string="Available Fiscal Type",
        comodel_name="account.fiscal.type",
        compute="_compute_available_fiscal_type",
    )
    fiscal_sequence_id = fields.Many2one(
        comodel_name="account.fiscal.sequence",
        string="Fiscal Sequence",
        copy=False,
        compute="_compute_fiscal_sequence",
        store=True,
    )
    income_type = fields.Selection(
        string="Income Type",
        selection=[
            ("01", "01 - Operating Revenues (Non-Financial)"),
            ("02", "02 - Financial Revenues"),
            ("03", "03 - Extraordinary Revenues"),
            ("04", "04 - Rental Revenues"),
            ("05", "05 - Revenues from Sale of Depreciable Assets"),
            ("06", "06 - Other Revenues"),
        ],
        copy=False,
        default=lambda self: self._context.get("income_type", "01"),
    )
    expense_type = fields.Selection(
        copy=False,
        selection=[
            ("01", "01 - Personnel Expenses"),
            ("02", "02 - Expenses for Labor, Supplies, and Services"),
            ("03", "03 - Leases"),
            ("04", "04 - Fixed Asset Expenses"),
            ("05", "05 - Representation Expenses"),
            ("06", "06 - Other Allowable Deductions"),
            ("07", "07 - Financial Expenses"),
            ("08", "08 - Extraordinary Expenses"),
            ("09", "09 - Purchases and Expenses that form part of the Cost of Sales"),
            ("10", "10 - Acquisitions of Assets"),
            ("11", "11 - Insurance Expenses"),
        ],
        string="Cost & Expense Type",
    )
    annulation_type = fields.Selection(
        string="Annulment Type",
        selection=[
            ("01", "01 - Deterioration of Pre-printed Invoice"),
            ("02", "02 - Printing Errors (Pre-printed Invoice)"),
            ("03", "03 - Defective Printing"),
            ("04", "04 - Correction of Information"),
            ("05", "05 - Change of Products"),
            ("06", "06 - Product Returns"),
            ("07", "07 - Omission of Products"),
            ("08", "08 - Errors in Sequence of NCF"),
            ("09", "09 - Due to Cessation of Operations"),
            ("10", "10 - Loss or Theft of Invoice Books"),
        ],
        copy=False,
    )
    origin_out = fields.Char(string="Affects", copy=False)
    ncf_expiration_date = fields.Date(string="Valid until", store=True, copy=False)

    is_l10n_do_fiscal_invoice = fields.Boolean(
        string="Is Fiscal Invoice",
        compute="_compute_is_l10n_do_fiscal_invoice",
        store=True,
    )
    assigned_sequence = fields.Boolean(related="fiscal_type_id.assigned_sequence")
    fiscal_sequence_status = fields.Selection(
        selection=[
            ("no_fiscal", "No fiscal"),
            ("fiscal_ok", "Ok"),
            ("almost_no_sequence", "Almost no sequence"),
            ("no_sequence", "Depleted"),
        ],
        compute="_compute_fiscal_sequence_status",
    )
    is_debit_note = fields.Boolean(string="Is debit note")

    @api.depends("is_l10n_do_fiscal_invoice", "move_type", "journal_id", "partner_id")
    def _compute_available_fiscal_type(self):
        for inv in self:
            inv.available_fiscal_type_ids = False
        for inv in self.filtered(
            lambda x: x.journal_id and x.is_l10n_do_fiscal_invoice and x.partner_id
        ):
            inv.available_fiscal_type_ids = self.env["account.fiscal.type"].search(
                inv._get_fiscal_domain()
            )

    def _get_fiscal_domain(self):
        return [("type", "=", self.move_type)]

    @api.depends("journal_id")
    def _compute_is_l10n_do_fiscal_invoice(self):
        for inv in self:
            inv.is_l10n_do_fiscal_invoice = bool(inv.journal_id.l10n_do_fiscal_journal)

    @api.depends(
        "journal_id",
        "is_l10n_do_fiscal_invoice",
        "state",
        "fiscal_type_id",
        "invoice_date",
        "move_type",
        "is_debit_note",
    )
    def _compute_fiscal_sequence(self):
        for inv in self.filtered(lambda i: i.state == "draft"):
            if inv.is_debit_note:
                debit_map = {"in_invoice": "in_debit", "out_invoice": "out_debit"}
                fiscal_type = self.env["account.fiscal.type"].search(
                    [("type", "=", debit_map[inv.move_type])], limit=1
                )
                inv.fiscal_type_id = fiscal_type.id
            else:
                fiscal_type = inv.fiscal_type_id

            if inv.is_l10n_do_fiscal_invoice and fiscal_type and fiscal_type.assigned_sequence:
                inv.fiscal_position_id = fiscal_type.fiscal_position_id

                domain = [
                    ("company_id", "=", inv.company_id.id),
                    ("fiscal_type_id", "=", fiscal_type.id),
                    ("state", "=", "active"),
                ]
                date_ref = inv.invoice_date or fields.Date.context_today(inv)
                domain.append(("expiration_date", ">=", date_ref))

                fiscal_sequence_id = inv.env["account.fiscal.sequence"].search(
                    domain, order="expiration_date, id desc", limit=1
                )
                inv.fiscal_sequence_id = fiscal_sequence_id or False
            else:
                inv.fiscal_sequence_id = False

    @api.depends(
        "fiscal_sequence_id",
        "fiscal_sequence_id.sequence_remaining",
        "fiscal_sequence_id.remaining_percentage",
        "state",
        "journal_id",
    )
    def _compute_fiscal_sequence_status(self):
        for inv in self:
            if not inv.is_l10n_do_fiscal_invoice or not inv.fiscal_sequence_id:
                inv.fiscal_sequence_status = "no_fiscal"
                continue

            fs = inv.fiscal_sequence_id
            remaining = fs.sequence_remaining
            warning_percentage = fs.remaining_percentage
            seq_length = fs.sequence_end - fs.sequence_start + 1

            remaining_percentage = round((remaining / seq_length), 2) * 100 if seq_length else 0

            if remaining_percentage > warning_percentage:
                inv.fiscal_sequence_status = "fiscal_ok"
            elif remaining > 0 and remaining_percentage <= warning_percentage:
                inv.fiscal_sequence_status = "almost_no_sequence"
            else:
                inv.fiscal_sequence_status = "no_sequence"

    @api.constrains("state", "invoice_line_ids", "partner_id")
    def validate_products_export_ncf(self):
        for inv in self:
            if (
                inv.move_type == "out_invoice"
                and inv.state in ("posted", "cancel")
                and inv.partner_id.country_id
                and inv.partner_id.country_id.code != "DO"
                and inv.is_l10n_do_fiscal_invoice
            ):
                if any(p for p in inv.invoice_line_ids.mapped("product_id") if p.type != "service"):
                    if ncf_dict.get(inv.fiscal_type_id.prefix) == "exterior":
                        raise UserError(_("Goods sales to overseas customers must have Exportaciones Fiscal Type"))
                elif ncf_dict.get(inv.fiscal_type_id.prefix) == "consumo":
                    raise UserError(_("Service sales to oversas customer must have Consumo Fiscal Type"))

    @api.onchange("journal_id", "partner_id")
    def _onchange_journal_id(self):
        if not self.is_l10n_do_fiscal_invoice:
            self.fiscal_type_id = False
            self.fiscal_sequence_id = False
        return super()._onchange_journal_id()

    @api.onchange("fiscal_type_id")
    def _onchange_fiscal_type(self):
        if self.is_l10n_do_fiscal_invoice and self.fiscal_type_id:
            if ncf_dict.get(self.fiscal_type_id.prefix) == "minor":
                self.partner_id = self.company_id.partner_id

            fiscal_type_journal = self.fiscal_type_id.journal_id
            if fiscal_type_journal and fiscal_type_journal != self.journal_id:
                self.journal_id = fiscal_type_journal

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.is_l10n_do_fiscal_invoice:
            fiscal_type_object = self.env["account.fiscal.type"]

            if self.partner_id and self.move_type == "out_invoice" and not self.fiscal_type_id:
                self.fiscal_type_id = self.partner_id.sale_fiscal_type_id

            elif self.partner_id and self.move_type == "in_invoice":
                self.expense_type = self.partner_id.expense_type

                if self.partner_id.id == self.company_id.partner_id.id:
                    fiscal_type = fiscal_type_object.search(
                        [("type", "=", self.move_type), ("prefix", "=", "B13")], limit=1
                    )
                    if not fiscal_type:
                        raise ValidationError(
                            _("A fiscal type for Minor Expenses does not exist and you have to create one.")
                        )
                    self.fiscal_type_id = fiscal_type
                    return super()._onchange_partner_id()

                self.fiscal_type_id = self.partner_id.purchase_fiscal_type_id

            elif self.partner_id and not self.fiscal_type_id and self.move_type in ["in_refund", "out_refund"]:
                fiscal_refund = fiscal_type_object.search([("type", "=", self.move_type)], limit=1)
                self.fiscal_type_id = fiscal_refund or False

        return super()._onchange_partner_id()

    def _post(self, soft=True):
        for inv in self:
            if inv.is_l10n_do_fiscal_invoice and inv.is_invoice():
                if inv.amount_total == 0:
                    raise UserError(_("You cannot validate an invoice whose total amount is equal to 0"))

                if inv.fiscal_type_id and not inv.fiscal_type_id.assigned_sequence:
                    inv.fiscal_type_id.check_format_fiscal_number(inv.ref)

                inv._compute_fiscal_sequence()

                if not inv.ref and not inv.fiscal_sequence_id and inv.fiscal_type_id.assigned_sequence:
                    raise ValidationError(_("There is not active Fiscal Sequence for this type of document."))

                if inv.fiscal_type_id.requires_document and not inv.partner_id.vat:
                    raise UserError(
                        _("Partner [{}] {} doesn't have RNC/Céd, is required for NCF type {}").format(
                            inv.partner_id.id, inv.partner_id.name, inv.fiscal_type_id.name
                        )
                    )

                if inv.move_type in ("out_invoice", "out_refund"):
                    if inv.amount_untaxed_signed >= 250000 and inv.fiscal_type_id.prefix != "B12" and not inv.partner_id.vat:
                        raise UserError(
                            _("if the invoice amount is greater than RD$250,000.00 the customer should have RNC or Céd for make invoice")
                        )

                if inv.origin_out and inv.move_type in ("out_refund", "in_refund"):
                    self.env["account.fiscal.type"].check_format_fiscal_number(
                        inv.origin_out,
                        "in_invoice" if inv.move_type == "in_refund" else "out_invoice",
                    )

                    origin_invoice = self.env["account.move"].search(
                        [
                            "|", "|",
                            ("partner_id", "=", inv.partner_id.id),
                            ("partner_id", "=", inv.partner_id.parent_id.id),
                            ("partner_id", "in", inv.partner_id.child_ids.ids),
                            ("ref", "=", inv.origin_out),
                            ("state", "=", "posted"),
                            ("is_l10n_do_fiscal_invoice", "=", True),
                            ("move_type", "=", "in_invoice" if inv.move_type == "in_refund" else "out_invoice"),
                        ],
                        limit=1,
                    )

                    if not origin_invoice:
                        raise UserError(
                            _("The invoice ({}) to which the credit note refers does not exist in the system or is not under the name of {}").format(
                                inv.origin_out, inv.partner_id.name
                            )
                        )

                    if inv.invoice_date and origin_invoice.invoice_date:
                        delta_time = inv.invoice_date - origin_invoice.invoice_date
                        if (
                            delta_time.days > 30
                            and inv.line_ids.filtered(lambda l: l.tax_line_id and "itbis" in l.tax_line_id.name.lower())
                        ):
                            raise UserError(
                                _("The invoice ({}) to which this credit note refers is more than 30 days old ({}), therefore the ITBIS tax must be removed.").format(
                                    inv.origin_out, delta_time.days
                                )
                            )

        res = super()._post(soft)

        for inv in self:
            if (
                inv.is_l10n_do_fiscal_invoice
                and not inv.ref
                and inv.fiscal_type_id.assigned_sequence
                and inv.is_invoice()
                and inv.state == "posted"
            ):
                inv.write(
                    {
                        "ref": inv.fiscal_sequence_id.get_fiscal_number(),
                        "ncf_expiration_date": inv.fiscal_sequence_id.expiration_date,
                    }
                )
        return res

    def action_invoice_cancel(self):
        fiscal_invoice = self.filtered(lambda inv: inv.journal_id.l10n_do_fiscal_journal)
        if len(fiscal_invoice) > 1:
            raise ValidationError(_("You cannot cancel multiple fiscal invoices at a time."))

        if fiscal_invoice:
            action = self.env.ref("l10n_do_accounting.action_account_invoice_cancel").read()[0]
            action["context"] = {"default_invoice_id": fiscal_invoice.id}
            return action

    def button_cancel(self):
        if self.journal_id.l10n_do_fiscal_journal and not self.env.context.get("l10n_do_force_cancel"):
            return self.action_invoice_cancel()
        return super().button_cancel()

    def _get_l10n_do_amounts(self, company_currency=False):
        self.ensure_one()
        amount_field = company_currency and "balance" or "price_subtotal"
        sign = -1 if (company_currency and self.is_inbound()) else 1

        itbis_tax_group = self.env.ref("l10n_do.group_itbis", False)

        taxed_move_lines = self.line_ids.filtered("tax_line_id")
        itbis_taxed_move_lines = taxed_move_lines.filtered(
            lambda l: itbis_tax_group in l.tax_line_id.mapped("tax_group_id") and l.tax_line_id.amount > 0
        )

        itbis_taxed_product_lines = self.invoice_line_ids.filtered(
            lambda l: itbis_tax_group in l.tax_ids.mapped("tax_group_id")
        )

        return {
            "itbis_amount": sign * sum(itbis_taxed_move_lines.mapped(amount_field)),
            "itbis_taxable_amount": sign
            * sum(
                line[amount_field]
                for line in itbis_taxed_product_lines
                if line.price_total != line.price_subtotal
            ),
            "itbis_exempt_amount": sign
            * sum(
                line[amount_field]
                for line in itbis_taxed_product_lines
                if any(True for tax in line.tax_ids if tax.amount == 0)
            ),
        }

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        fiscal_invoices = res.filtered(
            lambda i: i.is_l10n_do_fiscal_invoice and not i.fiscal_type_id and i.is_invoice()
        )
        for inv in fiscal_invoices:
            # Evitar onchange server-side agresivo: usa el compute del partner
            inv.fiscal_type_id = inv.partner_id.sale_fiscal_type_id
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_fiscal_invoice(self):
        for invoice in self:
            if invoice.is_l10n_do_fiscal_invoice and invoice.is_invoice() and invoice.ref:
                raise UserError(_("You cannot delete a fiscal invoice that has been validated."))
