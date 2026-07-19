import calendar
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date


class NovaRecurringItem(models.Model):
    _name = 'nova.recurring.item'
    _description = 'Recurring Cash Commitment'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    direction = fields.Selection(
        [('in', 'Inflow'), ('out', 'Outflow')], required=True, tracking=True,
    )
    category_id = fields.Many2one('nova.category', required=True, check_company=True)
    partner_id = fields.Many2one('res.partner', check_company=True)
    amount = fields.Monetary(required=True, tracking=True, help='Base amount; see Amount (Today) for the current effective amount (BR-08).')
    amount_today = fields.Monetary(compute='_compute_amount_today', string='Amount (Today)')
    currency_id = fields.Many2one(
        'res.currency', required=True, default=lambda self: self.env.company.currency_id.id,
    )
    frequency = fields.Selection([
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ], required=True, default='monthly', tracking=True)
    interval = fields.Integer(required=True, default=1, help='Every N frequency units.')
    day_rule = fields.Integer(
        help='Day of month (1-31); day 29-31 resolves to the last day of shorter months (BR-07).',
    )
    weekday = fields.Selection([
        ('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'), ('3', 'Thursday'),
        ('4', 'Friday'), ('5', 'Saturday'), ('6', 'Sunday'),
    ])
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    end_date = fields.Date()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('ended', 'Ended'),
    ], required=True, default='draft', tracking=True)
    next_occurrences = fields.Char(compute='_compute_next_occurrences', string='Next Occurrences')
    revision_ids = fields.One2many('nova.recurring.revision', 'item_id')

    @api.constrains('interval')
    def _check_interval(self):
        for rec in self:
            if rec.interval < 1:
                raise ValidationError(_("Interval must be at least 1."))

    @api.constrains('frequency', 'day_rule', 'weekday')
    def _check_schedule_fields(self):
        for rec in self:
            if rec.frequency == 'weekly' and not rec.weekday:
                raise ValidationError(_("Weekly recurring items require a weekday."))
            if rec.frequency in ('monthly', 'quarterly', 'yearly') and not rec.day_rule:
                raise ValidationError(_("Monthly, quarterly, and yearly recurring items require a day of month."))
            if rec.day_rule and not (1 <= rec.day_rule <= 31):
                raise ValidationError(_("Day of month must be between 1 and 31."))

    def write(self, vals):
        if 'amount' in vals and not self.env.context.get('nova_allow_amount_write'):
            for rec in self:
                if rec.state == 'active':
                    raise UserError(_(
                        "Use the 'Revise Amount' wizard to change the amount of an active recurring item (BR-08)."
                    ))
        return super().write(vals)

    def action_activate(self):
        for rec in self:
            rec._check_schedule_fields()
            rec.state = 'active'

    def action_end(self):
        for rec in self:
            rec.state = 'ended'
            if not rec.end_date:
                rec.end_date = fields.Date.context_today(self)

    def action_export_xlsx(self):
        """R-04: Recurring Commitments Register export."""
        records = self if self else self.search([])
        return {
            'type': 'ir.actions.act_url',
            'url': '/cashflow_pilot/export/recurring_xlsx?ids=%s' % ','.join(str(i) for i in records.ids),
            'target': 'download',
        }

    def _get_effective_amount(self, on_date):
        self.ensure_one()
        revisions = self.revision_ids.filtered(lambda r: r.effective_from <= on_date)
        revisions = revisions.sorted('effective_from', reverse=True)
        return revisions[0].amount if revisions else self.amount

    @api.depends('amount', 'revision_ids.amount', 'revision_ids.effective_from')
    def _compute_amount_today(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.amount_today = rec._get_effective_amount(today)

    @staticmethod
    def _resolve_month_day(year, month, day_rule):
        last_day = calendar.monthrange(year, month)[1]
        return min(day_rule, last_day)

    def _get_occurrence_dates(self, date_from, date_to):
        """BR-07: generate occurrence dates in [date_from, date_to], honoring
        interval/day_rule/weekday, one occurrence per period maximum.
        """
        self.ensure_one()
        dates = []
        if not self.start_date or date_from > date_to:
            return dates
        window_start = max(date_from, self.start_date)
        window_end = date_to
        if self.end_date:
            window_end = min(window_end, self.end_date)
        if window_start > window_end:
            return dates

        if self.frequency == 'weekly':
            target_weekday = int(self.weekday)
            step = timedelta(weeks=self.interval)
            current = self.start_date + timedelta(days=(target_weekday - self.start_date.weekday()) % 7)
            while current < window_start:
                current += step
            while current <= window_end:
                dates.append(current)
                current += step
        else:
            months_step = {'monthly': 1, 'quarterly': 3, 'yearly': 12}[self.frequency] * self.interval
            year, month = self.start_date.year, self.start_date.month
            current = date(year, month, self._resolve_month_day(year, month, self.day_rule))

            def _advance(y, m):
                m += months_step
                y += (m - 1) // 12
                m = (m - 1) % 12 + 1
                return y, m

            while current < window_start:
                year, month = _advance(year, month)
                current = date(year, month, self._resolve_month_day(year, month, self.day_rule))
            while current <= window_end:
                dates.append(current)
                year, month = _advance(year, month)
                current = date(year, month, self._resolve_month_day(year, month, self.day_rule))
        return dates

    @api.depends('frequency', 'interval', 'day_rule', 'weekday', 'start_date', 'end_date')
    def _compute_next_occurrences(self):
        today = fields.Date.context_today(self)
        window_end = today + relativedelta(years=2)
        for rec in self:
            if not rec.frequency or not rec.start_date or (rec.frequency == 'weekly' and not rec.weekday) \
                    or (rec.frequency != 'weekly' and not rec.day_rule):
                rec.next_occurrences = ''
                continue
            occurrences = rec._get_occurrence_dates(today, window_end)[:3]
            if occurrences:
                rec.next_occurrences = ', '.join(format_date(self.env, d) for d in occurrences)
            else:
                rec.next_occurrences = _('No upcoming occurrences')
