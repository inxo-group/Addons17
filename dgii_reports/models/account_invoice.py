import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class InvoiceServiceTypeDetail(models.Model):
    _name = "invoice.service.type.detail"
    _description = "Invoice Service Type Detail"

    name = fields.Char()
    code = fields.Char(size=2)
    parent_code = fields.Char()

    _sql_constraints = [
        ("code_unique", "unique(code)", _("Code must be unique")),
    ]


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_payment_widget(self):
        """
        Odoo puede exponer invoice_payments_widget como dict (JSON field)
        o como string JSON dependiendo de versión/contexto.
        """
        self.ensure_one()
        widget = self.invoice_payments_widget
        if not widget:
            return []

        if isinstance(widget, str):
            try:
                widget = json.loads(widget)
            except Exception:
                return []

        if isinstance(widget, dict):
            return widget.get("content", []) or []

        return []

    def _get_tax_line_ids(self):
        return self.line_ids.filtered(lambda l: l.tax_line_id)

    def _convert_to_local_currency(self, amount):
        self.ensure_one()
        sign = -1 if self.move_type in ("in_refund", "out_refund") else 1

        if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
            currency = self.currency_id.with_context(date=self.invoice_date or fields.Date.today())
            amount = currency.round(
                currency._convert(
                    amount,
                    self.company_id.currency_id,
                    self.company_id,
                    self.invoice_date or fields.Date.today(),
                )
            )

        return amount * sign

    @api.constrains("line_ids", "line_ids.tax_line_id")
    def _check_isr_tax(self):
        """Restrict one ISR/ritbis withholding tax per invoice."""
        for inv in self:
            types = [
                line.tax_line_id.l10n_do_tax_type
                for line in inv._get_tax_line_ids()
                if line.tax_line_id.l10n_do_tax_type in ("isr", "ritbis")
            ]
            if len(types) != len(set(types)):
                raise ValidationError(_("An invoice cannot have multiple withholding taxes."))

    @api.depends("payment_state", "invoice_date", "invoice_payments_widget")
    def _compute_invoice_payment_date(self):
        for inv in self:
            payment_date = False

            if inv.payment_state in ("paid", "in_payment"):
                dates = [p.get("date") for p in inv._get_invoice_payment_widget() if p.get("date")]
                if dates:
                    max_date = max(dates)
                    invoice_date = inv.invoice_date
                    payment_date = max_date if (invoice_date and max_date >= invoice_date) else invoice_date or max_date

            inv.payment_date = payment_date

    @api.depends("state", "line_ids", "line_ids.balance", "line_ids.tax_line_id")
    def _compute_taxes_fields(self):
        for inv in self:
            inv.invoiced_itbis = 0.0
            inv.selective_tax = 0.0
            inv.other_taxes = 0.0
            inv.legal_tip = 0.0
            inv.advance_itbis = 0.0

            inv.cost_itbis = 0.0
            inv.proportionality_tax = 0.0

            tax_lines = inv._get_tax_line_ids()
            if inv.state == "draft" or not tax_lines:
                continue

            inv.invoiced_itbis = abs(sum(tax_lines.filtered(lambda l: l.tax_line_id.l10n_do_tax_type == "itbis").mapped("balance")))
            inv.selective_tax = abs(sum(tax_lines.filtered(lambda l: l.tax_line_id.l10n_do_tax_type == "isc").mapped("balance")))
            inv.other_taxes = abs(sum(tax_lines.filtered(lambda l: l.tax_line_id.l10n_do_tax_type == "other").mapped("balance")))
            inv.legal_tip = abs(sum(tax_lines.filtered(lambda l: l.tax_line_id.l10n_do_tax_type == "tip").mapped("balance")))

            inv.advance_itbis = inv.invoiced_itbis - inv.cost_itbis


    @api.depends("state", "payment_state", "line_ids", "line_ids.balance", "line_ids.tax_line_id")
    def _compute_withholding_taxes(self):
        for inv in self:
            inv.withholding_itbis = 0.0
            inv.income_withholding = 0.0

            tax_lines = inv._get_tax_line_ids()
            if inv.state == "draft" or not tax_lines:
                continue

            if inv.payment_state in ("paid", "in_payment"):
                inv.withholding_itbis = abs(sum(tax_lines.filtered(lambda l: l.tax_line_id.l10n_do_tax_type == "ritbis").mapped("balance")))
                inv.income_withholding = abs(sum(tax_lines.filtered(lambda l: l.tax_line_id.l10n_do_tax_type == "isr").mapped("balance")))

    @api.depends("state", "invoice_date", "invoice_line_ids", "invoice_line_ids.product_id", "invoice_line_ids.price_subtotal")
    def _compute_amount_fields(self):
        for inv in self:
            service_amount = 0.0
            good_amount = 0.0

            if inv.state != "draft" and inv.invoice_date:
                for line in inv.invoice_line_ids:
                    subtotal = line.price_subtotal

                    if not line.product_id:
                        service_amount += subtotal
                    elif line.product_id.type in ("product", "consu"):
                        good_amount += subtotal
                    else:
                        service_amount += subtotal

                service_amount = inv._convert_to_local_currency(service_amount)
                good_amount = inv._convert_to_local_currency(good_amount)

            inv.service_total_amount = service_amount
            inv.good_total_amount = good_amount

    @api.depends("state", "move_type", "invoice_line_ids", "invoice_line_ids.tax_ids", "line_ids.tax_line_id")
    def _compute_isr_withholding_type(self):
        for inv in self:
            inv.isr_withholding_type = False

            if inv.move_type == "in_invoice" and inv.state != "draft":
                isr_lines = [
                    l.tax_line_id
                    for l in inv._get_tax_line_ids()
                    if l.tax_line_id.l10n_do_tax_type == "isr"
                ]
                if isr_lines:
                    inv.isr_withholding_type = isr_lines[0].isr_retention_type

    def _get_payment_string(self):
        self.ensure_one()

        payments = []
        p_string = ""

        for p in self._get_invoice_payment_widget():
            payment_id = self.env["account.payment"].browse(p.get("account_payment_id"))
            move_id = False

            if payment_id:
                if payment_id.journal_id.type in ("cash", "bank"):
                    p_string = payment_id.journal_id.payment_form

            if not payment_id:
                move_id = self.env["account.move"].browse(p.get("move_id"))
                if move_id:
                    p_string = "swap"

            payments.append(p_string if (payment_id or move_id) else "credit_note")

        methods = set(payments)
        if len(methods) == 1:
            return list(methods)[0]
        if len(methods) > 1:
            return "mixed"
        return False

    @api.depends("payment_state")
    def _compute_in_invoice_payment_form(self):
        payment_dict = {
            "cash": "01",
            "bank": "02",
            "card": "03",
            "credit": "04",
            "swap": "05",
            "credit_note": "06",
            "mixed": "07",
        }
        for inv in self:
            if inv.payment_state in ("paid", "in_payment"):
                inv.payment_form = payment_dict.get(inv._get_payment_string()) or "04"
            else:
                inv.payment_form = "04"

    @api.depends("fiscal_type_id")
    def _compute_is_exterior(self):
        for inv in self:
            inv.is_exterior = True if inv.fiscal_type_id and inv.fiscal_type_id.prefix in ("B17", False) else False

    @api.onchange("service_type")
    def onchange_service_type(self):
        self.service_type_detail = False
        return {"domain": {"service_type_detail": [("parent_code", "=", self.service_type)]}}

    @api.onchange("journal_id")
    def ext_onchange_journal_id(self):
        self.service_type = False
        self.service_type_detail = False

    service_total_amount = fields.Monetary(
        string="Service Total Amount",
        compute="_compute_amount_fields",
        currency_field="company_currency_id",
    )
    good_total_amount = fields.Monetary(
        string="Good Total Amount",
        compute="_compute_amount_fields",
        currency_field="company_currency_id",
    )

    invoiced_itbis = fields.Monetary(
        string="Invoiced ITBIS",
        compute="_compute_taxes_fields",
        currency_field="company_currency_id",
    )
    proportionality_tax = fields.Monetary(
        string="Proportionality Tax",
        compute="_compute_taxes_fields",
        currency_field="company_currency_id",
    )
    cost_itbis = fields.Monetary(
        string="Cost Itbis",
        compute="_compute_taxes_fields",
        currency_field="company_currency_id",
    )
    advance_itbis = fields.Monetary(
        string="Advanced ITBIS",
        compute="_compute_taxes_fields",
        currency_field="company_currency_id",
    )

    isr_withholding_type = fields.Char(
        string="ISR Withholding Type",
        compute="_compute_isr_withholding_type",
        size=2,
    )

    selective_tax = fields.Monetary(
        string="Selective Tax",
        compute="_compute_taxes_fields",
        currency_field="company_currency_id",
    )
    other_taxes = fields.Monetary(
        string="Other taxes",
        compute="_compute_taxes_fields",
        currency_field="company_currency_id",
    )
    legal_tip = fields.Monetary(
        string="Legal tip amount",
        compute="_compute_taxes_fields",
        currency_field="company_currency_id",
    )

    withholding_itbis = fields.Monetary(
        string="Withholding ITBIS",
        compute="_compute_withholding_taxes",
        currency_field="company_currency_id",
    )
    income_withholding = fields.Monetary(
        string="Income Withholding",
        compute="_compute_withholding_taxes",
        currency_field="company_currency_id",
    )

    payment_date = fields.Date(
        string="Payment date",
        compute="_compute_invoice_payment_date",
        store=True,
    )
    payment_form = fields.Selection(
        string="Payment form",
        selection=[
            ("01", "Cash"),
            ("02", "Check / Transfer / Deposit"),
            ("03", "Credit Card / Debit Card"),
            ("04", "Credit"),
            ("05", "Swap"),
            ("06", "Credit Note"),
            ("07", "Mixed"),
        ],
        compute="_compute_in_invoice_payment_form",
    )

    is_exterior = fields.Boolean(compute="_compute_is_exterior")

    service_type = fields.Selection(
        string="Service type",
        selection=[
            ("01", "Personnel Expenses"),
            ("02", "Expenses for Work, Supplies and Services"),
            ("03", "Rentals"),
            ("04", "Fixed Asset Expenses"),
            ("05", "Representation Expenses"),
            ("06", "Financial Expenses"),
            ("07", "Insurance Expenses"),
            ("08", "Royalties and Other Intangibles Expenses"),
        ],
    )
    service_type_detail = fields.Many2one(
        string="Service type detail",
        comodel_name="invoice.service.type.detail",
    )

    fiscal_status = fields.Selection(
        selection=[
            ("normal", "Partial"),
            ("done", "Reported"),
            ("blocked", "Not Sent"),
        ],
        copy=False,
        default="normal",
        help="* The 'Green' status means the invoice was sent to the DGII.\n"
             "* The 'Red' status means the invoice is in a DGII report but has not yet been sent to the DGII.\n"
             "* The 'Grey' status means Has not yet been reported or was partially reported.",
    )

    @api.model
    def norma_recompute(self):
        """
        Recompute stored computed fields for active invoices.
        Compatible fallback para cambios internos entre versiones.
        """
        invoices = self.browse(self.env.context.get("active_ids", []))
        if not invoices:
            return

        fields_to_compute = []
        for name, f in invoices._fields.items():
            if getattr(f, "store", False) and getattr(f, "compute", False):
                fields_to_compute.append(f)

        add_to_compute = getattr(self.env, "add_to_compute", None)
        if callable(add_to_compute):
            for f in fields_to_compute:
                add_to_compute(f, invoices)
            invoices.recompute()
            return

        add_todo = getattr(self.env, "add_todo", None)
        if callable(add_todo):
            for f in fields_to_compute:
                add_todo(f, invoices)
            invoices.recompute()
            return

        invoices.invalidate_recordset()
