from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaOnboardingWizard(NovaTestCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company

    def test_uc01_zero_journal_blocks_next(self):
        wizard = self.env['nova.onboarding.wizard'].create({
            'company_id': self.company.id,
            'journal_ids': [(5, 0, 0)],
        })
        with self.assertRaises(UserError):
            wizard.action_next()

    def test_uc01_full_flow_creates_forecast(self):
        journal = self.env['account.journal'].sudo().search([
            ('type', 'in', ('bank', 'cash')), ('company_id', '=', self.company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': 'Nova Onboarding Bank', 'type': 'bank', 'company_id': self.company.id,
            })

        wizard = self.env['nova.onboarding.wizard'].create({
            'company_id': self.company.id,
            'journal_ids': [(6, 0, journal.ids)],
            'min_threshold': 50000.0,
        })
        payroll_line = wizard.template_line_ids.filtered(lambda l: l.name == 'Payroll')
        self.assertTrue(payroll_line, "Default templates must include Payroll (FR-CFG-03).")
        payroll_line.write({'selected': True, 'amount': 100000.0})

        wizard.action_next()
        self.assertEqual(wizard.state, 'threshold')
        wizard.action_next()
        self.assertEqual(wizard.state, 'templates')
        wizard.action_next()
        self.assertEqual(wizard.state, 'readiness')
        wizard.action_next()
        self.assertEqual(wizard.state, 'done')
        wizard.action_finish()

        self.assertTrue(self.company.nova_onboarding_done)
        self.assertEqual(self.company.nova_journal_ids, journal)
        self.assertEqual(self.company.nova_min_threshold, 50000.0)

        payroll_item = self.env['nova.recurring.item'].search([
            ('company_id', '=', self.company.id), ('name', '=', 'Payroll'),
        ])
        self.assertTrue(payroll_item)
        self.assertEqual(payroll_item.state, 'active')

        report = self.env['nova.period.report'].search([
            ('company_id', '=', self.company.id), ('granularity', '=', 'week'),
        ], limit=1)
        self.assertTrue(report, "Finishing onboarding must render a forecast (AC-01/UC-01).")
