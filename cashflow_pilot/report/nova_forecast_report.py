from odoo import api, models


class ReportCashflowPilotForecast(models.AbstractModel):
    """Companion to the qweb-pdf ir.actions.report (R-01): the framework
    calls _get_report_values() to build the docs/data context actually
    passed to the template - a bare data= kwarg on _render_qweb_pdf is not
    enough on its own (confirmed against account's own
    report_hash_integrity, which follows the same pattern).
    """
    _name = 'report.cashflow_pilot.nova_report_forecast_pdf_document'
    _description = 'Cash Flow Forecast PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        return {
            'doc_ids': docids,
            'doc_model': 'res.company',
            'docs': self.env['res.company'].browse(docids),
            'data': data or {},
        }
