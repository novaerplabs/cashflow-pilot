from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaForecastEngine(NovaTestCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env['res.partner'].create({'name': 'Nova Engine Customer'})
        self.today = fields.Date.context_today(self.env['nova.forecast.line'])

    def _create_invoice(self, amount=1000.0, move_type='out_invoice', invoice_date=None):
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner.id,
            'invoice_date': invoice_date or self.today,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'quantity': 1,
                'price_unit': amount,
            })],
        })
        move.action_post()
        return move

    def _ensure_bank_journal(self):
        journal = self.env['account.journal'].sudo().search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', self.company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': 'Nova Test Bank',
                'type': 'bank',
                'company_id': self.company.id,
            })
        return journal

    def test_ac01_opening_balance_from_selected_journals(self):
        journal = self._ensure_bank_journal()
        self.company.nova_journal_ids = [(6, 0, journal.ids)]
        self._nova_rebaseline_ac10()

        self.company.action_refresh_forecast()

        expected_opening = self.env['nova.period.report']._compute_opening_balance(self.company)
        report = self.env['nova.period.report'].search([
            ('company_id', '=', self.company.id),
            ('granularity', '=', 'week'),
        ], order='period_start', limit=1)
        self.assertTrue(report, "Forecast should render after configuring journals and refreshing (AC-01).")
        self.assertEqual(report.opening, expected_opening)

    def test_ac02_partial_residual(self):
        move = self._create_invoice(amount=100000.0)
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids,
        ).create({'amount': 40000.0})
        payment_register._create_payments()
        self._nova_rebaseline_ac10()

        self.env['nova.move.info']._sync_move_info(self.company)
        self.env['nova.forecast.line']._rebuild(self.company)

        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        line = self.env['nova.forecast.line'].search([('move_info_id', '=', info.id)])
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.amount_effective, 60000.0, places=2)

    def test_ac07_drill_reconciliation(self):
        self._create_invoice(amount=5000.0)
        category = self.env['nova.category'].search([('direction', '=', 'out')], limit=1)
        self.env['nova.manual.item'].create({
            'name': 'One-off outflow',
            'direction': 'out',
            'category_id': category.id,
            'expected_date': self.today,
            'amount': 2000.0,
        })
        self._nova_rebaseline_ac10()

        self.company.action_refresh_forecast()

        report = self.env['nova.period.report'].search([
            ('company_id', '=', self.company.id),
            ('granularity', '=', 'week'),
        ], order='period_start', limit=1)
        lines = self.env['nova.forecast.line'].search([
            ('company_id', '=', self.company.id),
            ('period_start', '=', report.period_start),
            ('at_risk_excluded', '=', False),
        ])
        inflow = sum(lines.filtered(lambda l: l.direction == 'in').mapped('amount_effective'))
        outflow = sum(lines.filtered(lambda l: l.direction == 'out').mapped('amount_effective'))

        self.assertAlmostEqual(inflow, report.inflow, places=2, msg="Drill total must reconcile to the cell (AC-07).")
        self.assertAlmostEqual(outflow, report.outflow, places=2)
        self.assertAlmostEqual(report.opening + inflow + outflow, report.closing, places=2)

    def test_br12_excluded_at_risk_omitted_from_closing(self):
        move = self._create_invoice(amount=3000.0)
        self._nova_rebaseline_ac10()
        self.env['nova.move.info']._sync_move_info(self.company)
        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        info.write({'at_risk': True, 'exclude_from_forecast': True})

        self.env['nova.forecast.line']._rebuild(self.company)
        self.env['nova.period.report']._rebuild(self.company)

        line = self.env['nova.forecast.line'].search([('move_info_id', '=', info.id)])
        self.assertTrue(line.at_risk_excluded)

        report = self.env['nova.period.report'].search([
            ('company_id', '=', self.company.id),
            ('granularity', '=', 'week'),
            ('period_start', '=', line.period_start),
        ])
        self.assertEqual(report.inflow, 0.0, "at_risk excluded lines must be omitted from inflow/closing (BR-12).")

    def test_br04_overdue_lands_in_current_period(self):
        move = self._create_invoice(amount=1500.0, invoice_date=self.today - timedelta(days=60))
        self._nova_rebaseline_ac10()

        self.company.action_refresh_forecast()

        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        self.assertLess(info.effective_date, self.today)

        current_week_start = self.env['nova.forecast.line']._bucket_week_start(
            self.today, self.company.nova_week_start or 'mon', self.today,
        )
        line = self.env['nova.forecast.line'].search([('move_info_id', '=', info.id)])
        self.assertEqual(line.period_start, current_week_start,
                          "Overdue items must land in the current period, never dropped (BR-04).")
