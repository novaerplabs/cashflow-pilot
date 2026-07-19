from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaCategory(NovaTestCase):

    def test_default_categories_loaded(self):
        categories = self.env['nova.category'].search([('company_id', '=', False)])
        self.assertEqual(len(categories), 9)
        self.assertEqual(len(categories.filtered(lambda c: c.direction == 'in')), 2)
        self.assertEqual(len(categories.filtered(lambda c: c.direction == 'out')), 7)

    def test_duplicate_code_same_scope_blocked(self):
        with self.assertRaises(Exception):
            self.env['nova.category'].create({
                'name': 'Duplicate Collections',
                'code': 'CUST_COLLECT',
                'direction': 'in',
            })
