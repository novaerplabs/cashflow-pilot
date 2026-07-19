from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = ['res.company', 'mail.thread', 'mail.activity.mixin']

    nova_journal_ids = fields.Many2many(
        'account.journal', 'nova_company_journal_rel', 'company_id', 'journal_id',
        string='Cash Flow Journals',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', id)]",
        help='Bank/cash journals composing the cash position (BR-05).',
    )
    nova_min_threshold = fields.Monetary(
        string='Minimum Cash Threshold', currency_field='currency_id',
    )
    nova_horizon = fields.Selection([
        ('4', '4 Weeks'),
        ('13', '13 Weeks'),
        ('26', '26 Weeks'),
    ], default='13', required=True, string='Forecast Horizon')
    nova_week_start = fields.Selection([
        ('mon', 'Monday'), ('tue', 'Tuesday'), ('wed', 'Wednesday'), ('thu', 'Thursday'),
        ('fri', 'Friday'), ('sat', 'Saturday'), ('sun', 'Sunday'),
    ], default='mon', required=True, string='Week Start Day')
    nova_last_refresh = fields.Datetime(string='Cash Flow Last Refresh', readonly=True)
    nova_breach_state = fields.Selection([
        ('ok', 'OK'), ('breached', 'Breached'),
    ], default='ok', required=True, string='Cash Flow Breach State', tracking=True)
    nova_opening_override_active = fields.Boolean(string='Override Opening Balance')
    nova_opening_override = fields.Monetary(
        string='Opening Balance Override', currency_field='currency_id',
    )
    nova_opening_override_note = fields.Char(string='Override Reason')
    nova_onboarding_done = fields.Boolean(string='Cash Flow Onboarding Done', default=False)

    @api.constrains('nova_horizon')
    def _check_nova_horizon_requires_pro(self):
        # Q-01: Core gets 4/13 weeks; 26 weeks is Pro-only.
        pro_installed = self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'cashflow_pilot_pro'), ('state', '=', 'installed'),
        ])
        if not pro_installed:
            for company in self:
                if company.nova_horizon == '26':
                    raise ValidationError(_(
                        "The 26-week horizon requires CashFlow Pilot Pro. Choose 4 or 13 weeks."
                    ))

    @api.constrains('nova_opening_override_active', 'nova_opening_override_note')
    def _check_opening_override_note(self):
        # FR-CFG-07: a reason note is mandatory whenever the override is active.
        for company in self:
            if company.nova_opening_override_active and not company.nova_opening_override_note:
                raise ValidationError(_(
                    "A reason note is required when overriding the opening balance."
                ))

    def write(self, vals):
        # New nova_* fields only; core res.company fields/behavior untouched
        # (HR-3: additive extension, not a core override).
        override_fields = {'nova_opening_override_active', 'nova_opening_override', 'nova_opening_override_note'}
        touched = override_fields & set(vals.keys())
        res = super().write(vals)
        if touched:
            for company in self:
                if company.nova_opening_override_active:
                    company.message_post(body=_(
                        "Opening balance overridden to %(amount)s. Reason: %(note)s",
                        amount=company.nova_opening_override,
                        note=company.nova_opening_override_note or '',
                    ))
        return res

    def action_refresh_forecast(self):
        """Manual 'Refresh now' routine (README §8) - identical to the daily cron for one company."""
        self.ensure_one()
        self.env['nova.move.info']._sync_move_info(self)
        self.env['nova.forecast.line']._rebuild(self)
        self.env['nova.period.report']._rebuild(self)
        self._evaluate_breach_state()
        self.nova_last_refresh = fields.Datetime.now()
        return True

    @api.model
    def _cron_refresh_all_forecasts(self):
        for company in self.search([]):
            company.action_refresh_forecast()

    @api.model
    def action_refresh_forecast_current_company(self):
        """Cockpit 'Refresh now' RPC entry point - resolves the active
        company from the session context, mirroring get_cockpit_kpis/grid.
        """
        self.env.company.action_refresh_forecast()
        return True

    @api.model
    def get_onboarding_status(self):
        return {'onboarding_done': bool(self.env.company.nova_onboarding_done)}

    def _evaluate_breach_state(self):
        """BR-11: exactly one activity + one email per ok->breached transition;
        breached->ok is a silent log; unchanged state fires nothing.
        """
        self.ensure_one()
        reports = self.env['nova.period.report'].sudo().search([
            ('company_id', '=', self.id),
            ('granularity', '=', 'week'),
        ])
        new_state = 'breached' if any(reports.mapped('below_threshold')) else 'ok'
        if new_state == self.nova_breach_state:
            return
        if new_state == 'breached':
            self._trigger_breach_alert(reports)
        else:
            self.message_post(
                body=_("Cash flow recovered: no projected period is below the minimum threshold."),
                subtype_xmlid='mail.mt_note',
            )
        self.nova_breach_state = new_state

    def _trigger_breach_alert(self, reports):
        self.ensure_one()
        breached = reports.filtered('below_threshold')
        low_point = min(breached, key=lambda r: r.closing) if breached else self.env['nova.period.report']
        note = _("The forecast projects at least one period below the minimum cash threshold.")
        if low_point:
            note = _(
                "Low point: %(amount)s in the week of %(week)s (threshold %(threshold)s).",
                amount=low_point.closing, week=low_point.period_start, threshold=low_point.threshold,
            )

        managers = self.env['res.users'].sudo().search([
            ('group_ids', 'in', self.env.ref('cashflow_pilot.nova_group_manager').id),
            ('company_ids', 'in', self.id),
        ])
        for manager in managers:
            self.activity_schedule(
                act_type_xmlid='cashflow_pilot.nova_activity_type_breach_review',
                summary=_("Cash flow threshold breach"),
                note=note,
                user_id=manager.id,
            )
        template = self.env.ref('cashflow_pilot.nova_mail_template_breach_alert', raise_if_not_found=False)
        if template and managers:
            template.sudo().send_mail(self.id, force_send=False, email_values={
                'recipient_ids': [(6, 0, managers.mapped('partner_id').ids)],
            })

    def _get_cockpit_url(self):
        self.ensure_one()
        action = self.env.ref('cashflow_pilot.nova_cockpit_action', raise_if_not_found=False)
        if not action:
            return self.get_base_url()
        return f"{self.get_base_url()}/web#action={action.id}"
