from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Read-only display fields sourced from nova.move.info (AD-01/HR-2):
    # no writable or stored product fields live on this model.
    nova_move_info_id = fields.Many2one(
        'nova.move.info', compute='_compute_nova_move_info_id',
    )
    nova_expected_date = fields.Date(related='nova_move_info_id.expected_date', readonly=True)
    nova_effective_date = fields.Date(related='nova_move_info_id.effective_date', readonly=True)
    nova_at_risk = fields.Boolean(related='nova_move_info_id.at_risk', readonly=True)

    def _compute_nova_move_info_id(self):
        # sudo(): keeps the accounting form usable for non-CashFlow users;
        # actual UI exposure is gated by group_ids on the inherited view.
        infos = self.env['nova.move.info'].sudo().search([('move_id', 'in', self.ids)])
        info_by_move = {info.move_id.id: info for info in infos}
        for move in self:
            move.nova_move_info_id = info_by_move.get(move.id, False)

    def action_open_nova_move_info(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'nova.move.info',
            'view_mode': 'form',
            'res_id': self.nova_move_info_id.id,
            'target': 'current',
        }
