from odoo import api, fields, models, _
from odoo.exceptions import UserError

_STEP_ORDER = ['journals', 'threshold', 'templates', 'readiness', 'done']

_DEFAULT_TEMPLATES = [
    ('Payroll', 'PAYROLL'),
    ('Rent', 'RENT_UTIL'),
    ('Tax / GST / VAT', 'TAX_STAT'),
    ('Loan EMI', 'LOAN_FIN'),
    ('Utilities', 'RENT_UTIL'),
    ('Insurance', 'OTHER_EXP'),
]


class NovaOnboardingWizard(models.TransientModel):
    _name = 'nova.onboarding.wizard'
    _description = 'Cash Flow Onboarding Wizard'

    state = fields.Selection([
        ('journals', 'Journals'),
        ('threshold', 'Threshold'),
        ('templates', 'Recurring Templates'),
        ('readiness', 'Readiness'),
        ('done', 'Done'),
    ], default='journals', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    journal_ids = fields.Many2many(
        'account.journal', string='Bank/Cash Journals',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    min_threshold = fields.Monetary(string='Minimum Cash Threshold')
    template_line_ids = fields.One2many('nova.onboarding.wizard.template', 'wizard_id')
    readiness_issue_ids = fields.Many2many('nova.readiness.issue', compute='_compute_readiness_issue_ids')

    @api.model_create_multi
    def create(self, vals_list):
        """template_line_ids is populated here, purely server-side, rather
        than via default_get: the web client does not reliably round-trip
        a freshly-defaulted O2M sub-record's Char field back on creation
        (observed: category_id/Many2one survives, name/Char does not), so
        default_get is deliberately kept out of that loop entirely.
        """
        wizards = super().create(vals_list)
        for wizard in wizards:
            if not wizard.template_line_ids:
                wizard.template_line_ids = [(0, 0, line) for line in wizard._default_template_lines()]
        return wizards

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        company = self.env['res.company'].browse(vals['company_id']) if vals.get('company_id') else self.env.company
        if 'journal_ids' in fields_list and not vals.get('journal_ids'):
            journals = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')), ('company_id', '=', company.id),
            ])
            vals['journal_ids'] = [(6, 0, journals.ids)]
        if 'min_threshold' in fields_list and not vals.get('min_threshold'):
            vals['min_threshold'] = company.nova_min_threshold or 0.0
        return vals

    def _default_template_lines(self):
        fallback_category = self.env['nova.category'].search([('direction', '=', 'out')], limit=1)
        lines = []
        for name, code in _DEFAULT_TEMPLATES:
            category = self.env['nova.category'].search([('code', '=', code)], limit=1) or fallback_category
            lines.append({
                'name': name,
                'category_id': category.id,
                'frequency': 'monthly',
                'day_rule': 1,
                'selected': False,
                'amount': 0.0,
            })
        return lines

    def action_next(self):
        self.ensure_one()
        if self.state == 'journals':
            if not self.journal_ids:
                raise UserError(_("Select at least one bank or cash journal to continue."))
            self.state = 'threshold'
        elif self.state == 'threshold':
            self.state = 'templates'
        elif self.state == 'templates':
            self._create_recurring_items()
            self.state = 'readiness'
            self.env['nova.readiness.issue']._run_check(self.company_id)
        elif self.state == 'readiness':
            self.state = 'done'
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        index = _STEP_ORDER.index(self.state)
        if index > 0:
            self.state = _STEP_ORDER[index - 1]
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Onboarding Wizard'),
            'res_model': 'nova.onboarding.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }

    def _create_recurring_items(self):
        for line in self.template_line_ids.filtered('selected'):
            item = self.env['nova.recurring.item'].create({
                'name': line.name,
                'company_id': self.company_id.id,
                'direction': 'out',
                'category_id': line.category_id.id,
                'amount': line.amount,
                'frequency': line.frequency,
                'day_rule': line.day_rule,
                'start_date': fields.Date.context_today(self),
            })
            item.action_activate()

    @api.depends('company_id')
    def _compute_readiness_issue_ids(self):
        for wizard in self:
            wizard.readiness_issue_ids = self.env['nova.readiness.issue'].search([
                ('company_id', '=', wizard.company_id.id),
            ])

    def action_finish(self):
        self.ensure_one()
        self.company_id.nova_journal_ids = [(6, 0, self.journal_ids.ids)]
        self.company_id.nova_min_threshold = self.min_threshold
        self.company_id.nova_onboarding_done = True
        self.company_id.action_refresh_forecast()
        return {'type': 'ir.actions.client', 'tag': 'nova_cockpit'}
