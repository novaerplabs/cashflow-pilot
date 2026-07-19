from odoo import fields, models, _
from odoo.exceptions import UserError


class NovaRecurringReviseWizard(models.TransientModel):
    _name = 'nova.recurring.revise.wizard'
    _description = 'Revise Recurring Item Amount'

    item_id = fields.Many2one(
        'nova.recurring.item', required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    effective_from = fields.Date(required=True, default=fields.Date.context_today)
    new_amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='item_id.currency_id')

    def action_confirm(self):
        self.ensure_one()
        if self.item_id.state != 'active':
            raise UserError(_("Amount revisions apply only to active recurring items."))
        self.env['nova.recurring.revision'].create({
            'item_id': self.item_id.id,
            'effective_from': self.effective_from,
            'amount': self.new_amount,
        })
        return {'type': 'ir.actions.act_window_close'}
