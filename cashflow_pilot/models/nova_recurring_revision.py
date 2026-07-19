from odoo import fields, models


class NovaRecurringRevision(models.Model):
    _name = 'nova.recurring.revision'
    _description = 'Recurring Item Amount Revision'
    _order = 'effective_from desc'

    item_id = fields.Many2one(
        'nova.recurring.item', required=True, ondelete='cascade', index=True,
    )
    effective_from = fields.Date(required=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='item_id.currency_id', store=True)

    _sql_constraints = [
        ('item_effective_uniq', 'unique(item_id, effective_from)',
         'Only one revision per effective date is allowed for a recurring item.'),
    ]
