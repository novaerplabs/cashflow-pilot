from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaManualItem(NovaTestCase):

    def test_manual_item_state_flow(self):
        category = self.env['nova.category'].search([('direction', '=', 'in')], limit=1)
        item = self.env['nova.manual.item'].create({
            'name': 'Capital infusion',
            'direction': 'in',
            'category_id': category.id,
            'expected_date': fields.Date.context_today(self.env['nova.manual.item']),
            'amount': 100000.0,
        })
        self.assertEqual(item.state, 'planned')

        item.action_mark_realized()
        self.assertEqual(item.state, 'realized')
        self.assertTrue(item.realized_date)

    def test_manual_item_cancel(self):
        category = self.env['nova.category'].search([('direction', '=', 'out')], limit=1)
        item = self.env['nova.manual.item'].create({
            'name': 'One-off vendor payment',
            'direction': 'out',
            'category_id': category.id,
            'expected_date': fields.Date.context_today(self.env['nova.manual.item']),
            'amount': 2500.0,
        })
        item.action_cancel()
        self.assertEqual(item.state, 'cancelled')
