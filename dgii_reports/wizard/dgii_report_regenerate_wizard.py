from odoo import models, fields


class DgiiReportRegenerateWizard(models.TransientModel):
    """
    This wizard only objective is to show a warning when a dgii report
    is about to be regenerated.
    """
    _name = 'dgii.report.regenerate.wizard'
    _description = "DGII Report Regenerate Wizard"

    report_id = fields.Many2one(
        'dgii.reports',
        string='Report',
        readonly=True
    )

    def regenerate(self):
        report = self.env['dgii.reports'].browse(
            self.env.context.get('active_id')
        )
        if report:
            report._generate_report()
