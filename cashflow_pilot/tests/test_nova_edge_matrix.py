from datetime import date, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaEdgeMatrix(NovaTestCase):
    """README §17 edge matrix, core-side cases."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env['res.partner'].create({'name': 'Nova Edge Customer'})
        self.today = fields.Date.context_today(self.env['nova.forecast.line'])

    def _create_invoice(self, amount=1000.0, move_type='out_invoice', invoice_date=None, currency_id=None):
        vals = {
            'move_type': move_type,
            'partner_id': self.partner.id,
            'invoice_date': invoice_date or self.today,
            'invoice_line_ids': [(0, 0, {
                'name': 'Edge test line', 'quantity': 1, 'price_unit': amount,
            })],
        }
        if currency_id:
            vals['currency_id'] = currency_id
        move = self.env['account.move'].create(vals)
        move.action_post()
        return move

    def test_edge_missing_fx_rate_still_computes_at_last_known_rate(self):
        """BR-06: a currency with only a stale (>7-day-old) rate must still
        get its forecast line computed (at that last known rate), while the
        readiness check separately flags it - never a hard failure.
        """
        foreign = self.env['res.currency'].search([
            ('id', '!=', self.company.currency_id.id), ('active', '=', True),
        ], limit=1)
        foreign.ensure_one()
        self.env['res.currency.rate'].sudo().search([
            ('currency_id', '=', foreign.id), ('company_id', '=', self.company.id),
        ]).unlink()
        stale_rate = self.env['res.currency.rate'].sudo().create({
            'currency_id': foreign.id,
            'company_id': self.company.id,
            'name': self.today - timedelta(days=30),
            'rate': 2.0,
        })
        move = self._create_invoice(amount=100.0, currency_id=foreign.id)
        self._nova_rebaseline_ac10()

        self.company.action_refresh_forecast()

        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        self.assertTrue(info, "A foreign-currency invoice must still sync (BR-06 never blocks the engine).")
        self.assertNotEqual(
            info.residual_company, 0.0,
            "The line must still be computed using the last known (stale) rate, not zeroed out.",
        )

        self.env['nova.readiness.issue']._run_check(self.company)
        issue = self.env['nova.readiness.issue'].search([
            ('company_id', '=', self.company.id), ('issue_type', '=', 'missing_rate'),
        ])
        self.assertTrue(issue, "A currency with only a stale rate must be flagged as a readiness issue (BR-06).")
        stale_rate.unlink()

    def test_edge_month_end_recurring_31st_resolves_to_shorter_month_last_day(self):
        """BR-07: day_rule=31 on a monthly recurring item must resolve to
        the last day of February (28/29) rather than skip or overflow.
        """
        item = self.env['nova.recurring.item'].create({
            'name': 'Month-end rent',
            'direction': 'out',
            'category_id': self.env['nova.category'].search([('direction', '=', 'out')], limit=1).id,
            'partner_id': self.partner.id,
            'amount': 500.0,
            'frequency': 'monthly',
            'interval': 1,
            'day_rule': 31,
            'start_date': date(self.today.year, 1, 1),
        })
        occurrences = item._get_occurrence_dates(date(self.today.year, 1, 1), date(self.today.year, 4, 1))
        february_occurrences = [d for d in occurrences if d.month == 2]
        self.assertEqual(len(february_occurrences), 1)
        expected_last_day = 29 if (self.today.year % 4 == 0 and (self.today.year % 100 != 0 or self.today.year % 400 == 0)) else 28
        self.assertEqual(
            february_occurrences[0].day, expected_last_day,
            "BR-07: day_rule=31 must resolve to February's actual last day, not overflow into March.",
        )

    def test_edge_credit_note_both_directions(self):
        """BR-03: customer credit note is a negative inflow contribution
        (money owed back to the customer), vendor credit note is a
        positive outflow contribution (money owed back to us) - opposite
        signs from their corresponding invoice/bill.
        """
        customer_credit = self._create_invoice(amount=200.0, move_type='out_refund')
        vendor_credit = self._create_invoice(amount=150.0, move_type='in_refund')
        self._nova_rebaseline_ac10()

        self.company.action_refresh_forecast()

        customer_info = self.env['nova.move.info'].search([('move_id', '=', customer_credit.id)])
        vendor_info = self.env['nova.move.info'].search([('move_id', '=', vendor_credit.id)])

        self.assertEqual(customer_info.direction, 'in')
        self.assertLess(customer_info.residual_company, 0.0,
                         "BR-03: a customer credit note's residual must be negative.")

        self.assertEqual(vendor_info.direction, 'out')
        self.assertGreater(vendor_info.residual_company, 0.0,
                            "BR-03: a vendor credit note's residual must be positive.")

    def test_edge_sunday_week_start_company(self):
        """BR-04 bucketing must anchor on Sunday, not the mon default,
        when the company is configured with nova_week_start='sun'.
        """
        self.company.nova_week_start = 'sun'
        move = self._create_invoice(amount=300.0)
        self._nova_rebaseline_ac10()

        self.company.action_refresh_forecast()

        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        line = self.env['nova.forecast.line'].search([('move_info_id', '=', info.id)])
        self.assertEqual(
            line.period_start.weekday(), 6,
            "With nova_week_start='sun', every bucketed period must start on a Sunday (weekday()==6).",
        )

    def test_edge_zero_journals_selected_company(self):
        """§17: a company with no journals selected must still produce a
        forecast (opening balance simply reads 0.0, BR-05) rather than
        error out.
        """
        self.company.nova_journal_ids = [(5, 0, 0)]
        move = self._create_invoice(amount=400.0)
        self._nova_rebaseline_ac10()

        self.company.action_refresh_forecast()

        opening = self.env['nova.period.report']._compute_opening_balance(self.company)
        self.assertEqual(opening, 0.0, "BR-05: zero journals selected must yield a 0.0 opening balance, not error.")
        report = self.env['nova.period.report'].search([
            ('company_id', '=', self.company.id), ('granularity', '=', 'week'),
        ], order='period_start', limit=1)
        self.assertTrue(report, "The forecast must still materialize even with no journals selected.")
        self.assertEqual(report.opening, 0.0)
