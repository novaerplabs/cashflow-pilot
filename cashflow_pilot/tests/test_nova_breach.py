from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaBreach(NovaTestCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.manager = self.env['res.users'].create({
            'name': 'Nova Manager',
            'login': 'nova_manager_test',
            'email': 'nova_manager_test@example.com',
            'group_ids': [(6, 0, [self.env.ref('cashflow_pilot.nova_group_manager').id])],
            'company_ids': [(6, 0, [self.company.id])],
            'company_id': self.company.id,
        })
        journal = self.env['account.journal'].sudo().search([
            ('type', 'in', ('bank', 'cash')), ('company_id', '=', self.company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': 'Nova Breach Bank', 'type': 'bank', 'company_id': self.company.id,
            })
        self.company.nova_journal_ids = [(6, 0, journal.ids)]
        self._nova_rebaseline_ac10()

    def _activity_count(self):
        return self.env['mail.activity'].search_count([
            ('res_model', '=', 'res.company'), ('res_id', '=', self.company.id),
        ])

    def test_ac06_breach_single_fire(self):
        self.assertEqual(self.company.nova_breach_state, 'ok')
        self.company.nova_min_threshold = 10 ** 9  # trivially breached regardless of data

        self.company.action_refresh_forecast()
        self.assertEqual(self.company.nova_breach_state, 'breached')
        activities_after_first = self._activity_count()
        self.assertGreater(activities_after_first, 0,
                            "Transition to breached must create an activity for each manager.")

        self.company.action_refresh_forecast()
        self.assertEqual(self._activity_count(), activities_after_first,
                          "No repeat alert while the breach state is unchanged (BR-11).")

    def test_breach_recovery_is_silent(self):
        self.company.nova_min_threshold = 10 ** 9
        self.company.action_refresh_forecast()
        self.assertEqual(self.company.nova_breach_state, 'breached')
        activities_while_breached = self._activity_count()

        self.company.nova_min_threshold = -(10 ** 9)  # trivially satisfied -> recovers
        self.company.action_refresh_forecast()

        self.assertEqual(self.company.nova_breach_state, 'ok')
        self.assertEqual(self._activity_count(), activities_while_breached,
                          "Recovery must be a silent log, not a new activity (BR-11).")
