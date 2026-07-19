from odoo import fields
from odoo.http import Controller, request, route, content_disposition
from odoo.tools import format_date


class NovaPdfExportController(Controller):
    """R-01: simple QWeb PDF of the grid."""

    @route('/cashflow_pilot/export/forecast_pdf', type='http', auth='user', readonly=True)
    def export_forecast_pdf(self, granularity='week'):
        company = request.env.company
        reports = request.env['nova.period.report'].search([
            ('company_id', '=', company.id),
            ('granularity', '=', granularity),
        ], order='period_start')
        data = {
            'periods': [{
                # Short, locale-aware label (NFR-06) - a 13/26-column grid
                # needs a compact header, the full ISO date is too wide.
                'period_start': format_date(request.env, r.period_start, date_format='d MMM'),
                'opening': r.opening,
                'inflow': r.inflow,
                'outflow': r.outflow,
                'net': r.net,
                'closing': r.closing,
                'below_threshold': r.below_threshold,
            } for r in reports],
        }
        pdf_content, _report_type = request.env['ir.actions.report']._render_qweb_pdf(
            'cashflow_pilot.nova_report_forecast_pdf', res_ids=company.ids, data=data,
        )
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition('Cash Flow Forecast.pdf')),
        ]
        return request.make_response(pdf_content, headers)
