from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    nova_journal_ids = fields.Many2many(related='company_id.nova_journal_ids', readonly=False)
    nova_min_threshold = fields.Monetary(related='company_id.nova_min_threshold', readonly=False)
    nova_horizon = fields.Selection(related='company_id.nova_horizon', readonly=False)
    nova_week_start = fields.Selection(related='company_id.nova_week_start', readonly=False)
    nova_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')
    nova_opening_override_active = fields.Boolean(
        related='company_id.nova_opening_override_active', readonly=False,
    )
    nova_opening_override = fields.Monetary(related='company_id.nova_opening_override', readonly=False)
    nova_opening_override_note = fields.Char(related='company_id.nova_opening_override_note', readonly=False)
