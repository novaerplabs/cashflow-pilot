from odoo import fields, models


class NovaOnboardingWizardTemplate(models.TransientModel):
    _name = 'nova.onboarding.wizard.template'
    _description = 'Cash Flow Onboarding Recurring Template Line'

    wizard_id = fields.Many2one('nova.onboarding.wizard', required=True, ondelete='cascade')
    selected = fields.Boolean()
    name = fields.Char()
    category_id = fields.Many2one('nova.category')
    frequency = fields.Selection([
        ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('yearly', 'Yearly'),
    ], default='monthly')
    day_rule = fields.Integer(default=1)
    amount = fields.Monetary()
    currency_id = fields.Many2one(related='wizard_id.currency_id')
