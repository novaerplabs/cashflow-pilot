from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_core')
class TestNovaBulkReschedule(NovaTestCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Nova Bulk Reschedule Customer'})

    def _create_invoice(self, amount=1000.0):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.context_today(self.env['account.move']),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line', 'quantity': 1, 'price_unit': amount,
            })],
        })
        move.action_post()
        return move

    def test_bulk_reschedule_shift_days(self):
        move1 = self._create_invoice(2000.0)
        move2 = self._create_invoice(3000.0)
        self._nova_rebaseline_ac10()

        self.env['nova.move.info']._sync_move_info(self.env.company)
        infos = self.env['nova.move.info'].search([
            ('move_id', 'in', (move1 | move2).ids),
        ])
        original_dates = {info.id: info.effective_date for info in infos}

        wizard = self.env['nova.bulk.reschedule.wizard'].create({
            'move_info_ids': [(6, 0, infos.ids)],
            'mode': 'shift',
            'shift_days': 14,
        })
        wizard.action_confirm()

        for info in infos:
            self.assertEqual(info.expected_date, original_dates[info.id] + timedelta(days=14))

    def test_bulk_reschedule_set_date(self):
        move = self._create_invoice(1500.0)
        self._nova_rebaseline_ac10()

        self.env['nova.move.info']._sync_move_info(self.env.company)
        info = self.env['nova.move.info'].search([('move_id', '=', move.id)])
        target_date = fields.Date.context_today(self.env['account.move']) + timedelta(days=30)

        wizard = self.env['nova.bulk.reschedule.wizard'].create({
            'move_info_ids': [(6, 0, info.ids)],
            'mode': 'set_date',
            'new_date': target_date,
        })
        wizard.action_confirm()

        self.assertEqual(info.expected_date, target_date)
        # Accounting untouched is verified by the AC-10 fixture in cleanup.
