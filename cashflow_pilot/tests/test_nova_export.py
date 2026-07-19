from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaExportHttp(HttpCase):

    def test_export_forecast_xlsx_downloads(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/cashflow_pilot/export/forecast_xlsx?granularity=week')
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheet', response.headers.get('Content-Type', ''))

    def test_export_forecast_pdf_downloads(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/cashflow_pilot/export/forecast_pdf?granularity=week')
        self.assertEqual(response.status_code, 200)

    def test_export_move_info_xlsx_downloads(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/cashflow_pilot/export/move_info_xlsx?ids=')
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheet', response.headers.get('Content-Type', ''))

    def test_export_recurring_xlsx_downloads(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/cashflow_pilot/export/recurring_xlsx?ids=')
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheet', response.headers.get('Content-Type', ''))
