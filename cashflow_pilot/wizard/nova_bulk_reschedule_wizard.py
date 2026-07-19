from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NovaBulkRescheduleWizard(models.TransientModel):
    """Batch form of the single-item expected-date edit (FR-VIEW-05 /
    FR-IN-03 / FR-OUT-02): never touches accounting, writes only via
    nova.move.info, then runs one targeted recompute for the whole batch.
    Not specified by a dedicated FR/UC in the BRS - only named in the P4
    build-plan headline and the wizard/ directory comment - so this
    mirrors the already-specified single-item mechanics rather than
    inventing new ones.
    """
    _name = 'nova.bulk.reschedule.wizard'
    _description = 'Bulk Reschedule Expected Dates'

    move_info_ids = fields.Many2many('nova.move.info', string='Documents')
    mode = fields.Selection([
        ('shift', 'Shift by days'),
        ('set_date', 'Set to a specific date'),
    ], required=True, default='shift')
    shift_days = fields.Integer(string='Shift by (days)', default=7)
    new_date = fields.Date(string='New Expected Date', default=fields.Date.context_today)

    def action_confirm(self):
        self.ensure_one()
        if not self.move_info_ids:
            raise UserError(_("Select at least one document to reschedule."))
        for info in self.move_info_ids:
            if self.mode == 'shift':
                base_date = info.expected_date or info.effective_date
                info.expected_date = base_date + timedelta(days=self.shift_days)
            else:
                info.expected_date = self.new_date
        self.move_info_ids.action_targeted_recompute()
        return {'type': 'ir.actions.act_window_close'}
