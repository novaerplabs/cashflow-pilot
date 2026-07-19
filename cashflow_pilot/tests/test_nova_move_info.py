from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaMoveInfo(NovaTestCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Nova Test Customer'})

    def _create_invoice(self, move_type='out_invoice', **kwargs):
        vals = {
            'move_type': move_type,
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.to_date('2026-07-01'),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'quantity': 1,
                'price_unit': 1000.0,
            })],
        }
        vals.update(kwargs)
        move = self.env['account.move'].create(vals)
        move.action_post()
        self._nova_rebaseline_ac10()  # fixture created above; only what follows is checked for AC-10
        return move

    def test_ac03_due_date_fallback(self):
        self.partner.property_payment_term_id = False
        move = self._create_invoice(invoice_date_due=False)
        self.env['nova.move.info']._sync_move_info(self.env.company)
        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        self.assertTrue(info, "Satellite record should have been created for a posted move with residual.")
        self.assertFalse(info.due_date)
        self.assertEqual(info.effective_date, move.invoice_date)

    def test_ac04_expected_date_audit(self):
        move = self._create_invoice()
        self.env['nova.move.info']._sync_move_info(self.env.company)
        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        move_write_date_before = move.write_date

        info.expected_date = fields.Date.to_date('2026-08-15')

        self.assertEqual(info.effective_date, info.expected_date)
        self.assertEqual(move.write_date, move_write_date_before, "Accounting document must be unchanged (BR-18).")

        tracking = info.message_ids.mapped('tracking_value_ids').filtered(
            lambda t: t.field_id.name == 'expected_date'
        )
        self.assertTrue(tracking, "Expected-date change was not logged (FR-SEC-02).")

    def test_ac13_at_risk_exclusion_flags_stored(self):
        move = self._create_invoice()
        self.env['nova.move.info']._sync_move_info(self.env.company)
        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])

        info.write({'at_risk': True, 'exclude_from_forecast': True, 'risk_note': 'Disputed'})

        self.assertTrue(info.at_risk)
        self.assertTrue(info.exclude_from_forecast)
        self.assertEqual(info.risk_note, 'Disputed')

    def test_residual_company_sign_convention(self):
        move = self._create_invoice()
        self.env['nova.move.info']._sync_move_info(self.env.company)
        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        self.assertEqual(info.direction, 'in')
        self.assertGreater(info.residual_company, 0)
