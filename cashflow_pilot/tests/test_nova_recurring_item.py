from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaRecurringItem(NovaTestCase):

    def setUp(self):
        super().setUp()
        self.category = self.env['nova.category'].search([('direction', '=', 'out')], limit=1)
        self.today = fields.Date.context_today(self.env['nova.recurring.item'])

    def _create_item(self, **kwargs):
        vals = {
            'name': 'Rent',
            'direction': 'out',
            'category_id': self.category.id,
            'amount': 5000.0,
            'frequency': 'monthly',
            'interval': 1,
            'day_rule': 1,
            'start_date': self.today.replace(day=1),
        }
        vals.update(kwargs)
        return self.env['nova.recurring.item'].create(vals)

    def test_ac05_recurring_lifecycle(self):
        item = self._create_item()
        item.action_activate()
        self.assertEqual(item.state, 'active')

        occurrences = item._get_occurrence_dates(self.today, self.today + timedelta(days=400))
        self.assertGreaterEqual(len(occurrences), 12, "A monthly item should occur once per applicable period.")

        item.action_end()
        self.assertEqual(item.state, 'ended')
        self.assertTrue(item.end_date)

        future_occurrences = item._get_occurrence_dates(self.today, self.today + timedelta(days=400))
        self.assertTrue(all(d <= item.end_date for d in future_occurrences),
                         "Ending an item must drop future occurrences only; nothing past end_date should generate.")

    def test_month_end_day_rule_resolves_to_last_day(self):
        item = self._create_item(day_rule=31, start_date=fields.Date.to_date('2026-01-15'))
        occurrences = item._get_occurrence_dates(
            fields.Date.to_date('2026-02-01'), fields.Date.to_date('2026-02-28'),
        )
        self.assertEqual(occurrences, [fields.Date.to_date('2026-02-28')],
                          "Day 31 in a shorter month must resolve to that month's last day (BR-07).")

    def test_amount_locked_when_active_requires_wizard(self):
        item = self._create_item()
        item.action_activate()

        with self.assertRaises(Exception):
            item.write({'amount': 6000.0})

        wizard = self.env['nova.recurring.revise.wizard'].create({
            'item_id': item.id,
            'effective_from': self.today,
            'new_amount': 6000.0,
        })
        wizard.action_confirm()

        self.assertEqual(item.amount, 5000.0, "Base amount must never be mutated by a revision (BR-08).")
        self.assertEqual(item.amount_today, 6000.0)
