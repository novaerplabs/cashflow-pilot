from odoo import fields, models


class NovaManualItem(models.Model):
    _name = 'nova.manual.item'
    _description = 'Planned One-off Cash Item'
    _inherit = ['mail.thread']
    _order = 'expected_date'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    direction = fields.Selection(
        [('in', 'Inflow'), ('out', 'Outflow')], required=True, tracking=True,
    )
    category_id = fields.Many2one('nova.category', required=True, check_company=True)
    partner_id = fields.Many2one('res.partner', check_company=True)
    expected_date = fields.Date(required=True, index=True, tracking=True)
    amount = fields.Monetary(required=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', required=True, default=lambda self: self.env.company.currency_id.id,
    )
    state = fields.Selection([
        ('planned', 'Planned'),
        ('realized', 'Realized'),
        ('cancelled', 'Cancelled'),
    ], required=True, default='planned', tracking=True)
    realized_date = fields.Date()
    note = fields.Text()

    def action_mark_realized(self):
        for rec in self:
            rec.realized_date = rec.realized_date or fields.Date.context_today(self)
            rec.state = 'realized'

    def action_cancel(self):
        self.state = 'cancelled'
