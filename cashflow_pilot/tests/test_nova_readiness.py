from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaReadiness(NovaTestCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env['res.partner'].create({'name': 'Nova Readiness Customer'})
        self.partner.property_payment_term_id = False

    def test_ac03_readiness_check_flags_missing_due_date(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.context_today(self.env['account.move']),
            'invoice_date_due': False,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line', 'quantity': 1, 'price_unit': 500.0,
            })],
        })
        move.action_post()
        self._nova_rebaseline_ac10()

        self.env['nova.readiness.issue']._run_check(self.company)

        issue = self.env['nova.readiness.issue'].search([
            ('company_id', '=', self.company.id),
            ('issue_type', '=', 'no_due_date'),
        ])
        self.assertTrue(issue, "A posted move without a due date must be flagged (AC-03/BR-21a).")
        self.assertGreaterEqual(issue.record_count, 1)

    def test_readiness_check_rebuilds_fresh_each_run(self):
        self.env['nova.readiness.issue']._run_check(self.company)
        first_count = self.env['nova.readiness.issue'].search_count([('company_id', '=', self.company.id)])
        self.env['nova.readiness.issue']._run_check(self.company)
        second_count = self.env['nova.readiness.issue'].search_count([('company_id', '=', self.company.id)])
        self.assertEqual(first_count, second_count, "Each run must replace, not accumulate, issue rows.")
