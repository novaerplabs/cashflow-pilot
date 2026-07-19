from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _


class NovaPeriodReport(models.Model):
    _name = 'nova.period.report'
    _description = 'Cash Flow Period Report'
    _order = 'period_start'
    _rec_name = 'period_start'

    company_id = fields.Many2one('res.company', required=True, index=True)
    period_start = fields.Date(required=True, index=True)
    period_end = fields.Date(required=True)
    granularity = fields.Selection([('week', 'Week'), ('month', 'Month')], required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, string='Company Currency')
    opening = fields.Monetary(currency_field='currency_id')
    inflow = fields.Monetary(currency_field='currency_id')
    outflow = fields.Monetary(currency_field='currency_id')
    net = fields.Monetary(currency_field='currency_id')
    closing = fields.Monetary(currency_field='currency_id')
    threshold = fields.Monetary(currency_field='currency_id')
    below_threshold = fields.Boolean(index=True)

    @api.model
    def _scenario_base_domain(self):
        """See nova.forecast.line._scenario_base_domain - same forward
        guard, kept separately since this model has its own scenario_id
        once Pro is installed.
        """
        return [('scenario_id', '=', False)] if 'scenario_id' in self._fields else []

    def _rebuild(self, companies):
        """BR-17: delete + rebuild per company. Aggregates from the
        nova.forecast.line table only - callers that changed source
        documents must rebuild forecast lines first.
        """
        self_sudo = self.sudo()
        existing = self_sudo.search([('company_id', 'in', companies.ids)] + self._scenario_base_domain())
        if existing:
            existing.unlink()
        vals_list = []
        for company in companies:
            vals_list += self_sudo._build_weekly_reports(company)
            vals_list += self_sudo._build_monthly_reports(company)
        for i in range(0, len(vals_list), 1000):
            self_sudo.create(vals_list[i:i + 1000])
        return True

    def _compute_opening_balance(self, company):
        """BR-05: sum of posted balance of selected journals' liquidity
        accounts up to and including the day before forecast start (today).
        account.move.line.balance is always company-currency, so no
        conversion is needed here.

        FR-CFG-07: a manual override, when active, replaces the computed
        figure outright; the cockpit badges this and the change is
        chatter-logged on write (res.company.write override).
        """
        if company.nova_opening_override_active:
            return company.nova_opening_override
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        accounts = company.nova_journal_ids.mapped('default_account_id')
        if not accounts:
            return 0.0
        lines = self.env['account.move.line'].sudo().search([
            ('account_id', 'in', accounts.ids),
            ('move_id.state', '=', 'posted'),
            ('date', '<=', yesterday),
            ('company_id', '=', company.id),
        ])
        return sum(lines.mapped('balance'))

    def _build_weekly_reports(self, company):
        today = fields.Date.context_today(self)
        week_start_day = company.nova_week_start or 'mon'
        horizon_weeks = int(company.nova_horizon or '13')
        threshold = company.nova_min_threshold or 0.0
        current_week_start = self.env['nova.forecast.line']._bucket_week_start(today, week_start_day, today)
        opening = self._compute_opening_balance(company)

        forecast_line_model = self.env['nova.forecast.line']
        lines = forecast_line_model.sudo().search([
            ('company_id', '=', company.id),
            ('at_risk_excluded', '=', False),
        ] + forecast_line_model._scenario_base_domain())
        vals_list = []
        running_opening = opening
        for week_index in range(horizon_weeks):
            period_start = current_week_start + timedelta(weeks=week_index)
            period_end = period_start + timedelta(days=6)
            period_lines = lines.filtered(lambda l, ps=period_start: l.period_start == ps)
            inflow = sum(period_lines.filtered(lambda l: l.direction == 'in').mapped('amount_effective'))
            outflow = sum(period_lines.filtered(lambda l: l.direction == 'out').mapped('amount_effective'))
            net = inflow + outflow
            closing = running_opening + net
            vals_list.append({
                'company_id': company.id,
                'period_start': period_start,
                'period_end': period_end,
                'granularity': 'week',
                'opening': running_opening,
                'inflow': inflow,
                'outflow': outflow,
                'net': net,
                'closing': closing,
                'threshold': threshold,
                'below_threshold': closing < threshold,
            })
            running_opening = closing
        return vals_list

    def _build_monthly_reports(self, company):
        today = fields.Date.context_today(self)
        threshold = company.nova_min_threshold or 0.0
        opening = self._compute_opening_balance(company)

        forecast_line_model = self.env['nova.forecast.line']
        lines = forecast_line_model.sudo().search([
            ('company_id', '=', company.id),
            ('at_risk_excluded', '=', False),
        ] + forecast_line_model._scenario_base_domain())
        vals_list = []
        running_opening = opening
        month_start = today.replace(day=1)
        for _index in range(12):
            next_month_start = month_start + relativedelta(months=1)
            month_end = next_month_start - timedelta(days=1)
            period_lines = lines.filtered(
                lambda l, ms=month_start: forecast_line_model._bucket_month_start(l.expected_date, today) == ms
            )
            inflow = sum(period_lines.filtered(lambda l: l.direction == 'in').mapped('amount_effective'))
            outflow = sum(period_lines.filtered(lambda l: l.direction == 'out').mapped('amount_effective'))
            net = inflow + outflow
            closing = running_opening + net
            vals_list.append({
                'company_id': company.id,
                'period_start': month_start,
                'period_end': month_end,
                'granularity': 'month',
                'opening': running_opening,
                'inflow': inflow,
                'outflow': outflow,
                'net': net,
                'closing': closing,
                'threshold': threshold,
                'below_threshold': closing < threshold,
            })
            running_opening = closing
            month_start = next_month_start
        return vals_list

    # -- Cockpit facade (README §10.2) ------------------------------------
    # Read-only RPC surface consumed by the OWL cockpit. Uses self.env.company
    # (resolved server-side from the authenticated session's active company)
    # rather than a client-supplied company id, so ACL + the multi-company
    # record rule stay meaningful and a user can never RPC their way into
    # another company's cash position. Never triggers a rebuild itself.

    @api.model
    def get_cockpit_kpis(self):
        company = self.env.company
        reports = self.search([
            ('company_id', '=', company.id),
            ('granularity', '=', 'week'),
        ] + self._scenario_base_domain(), order='period_start')
        if not reports:
            return {
                'has_data': False,
                'currency_id': company.currency_id.id,
                'breach_state': company.nova_breach_state,
                'last_refresh': fields.Datetime.to_string(company.nova_last_refresh) if company.nova_last_refresh else False,
            }
        low_report = min(reports, key=lambda r: r.closing)
        runway_weeks = False
        for index, report in enumerate(reports):
            if report.closing < report.threshold:
                runway_weeks = index
                break
        return {
            'has_data': True,
            'cash_today': reports[0].opening,
            'opening_override_active': bool(company.nova_opening_override_active),
            'low_point': low_report.closing,
            'low_point_week': fields.Date.to_string(low_report.period_start),
            'runway_weeks': runway_weeks,
            'net_4week_flow': sum(reports[:4].mapped('net')),
            'currency_id': company.currency_id.id,
            'breach_state': company.nova_breach_state,
            'last_refresh': fields.Datetime.to_string(company.nova_last_refresh) if company.nova_last_refresh else False,
        }

    @api.model
    def get_cockpit_grid(self, granularity='week'):
        company_id = self.env.company.id
        reports = self.search([
            ('company_id', '=', company_id),
            ('granularity', '=', granularity),
        ] + self._scenario_base_domain(), order='period_start')
        periods = [{
            'period_start': fields.Date.to_string(r.period_start),
            'period_end': fields.Date.to_string(r.period_end),
            'opening': r.opening,
            'inflow': r.inflow,
            'outflow': r.outflow,
            'net': r.net,
            'closing': r.closing,
            'threshold': r.threshold,
            'below_threshold': r.below_threshold,
        } for r in reports]

        today = fields.Date.context_today(self)
        forecast_line_model = self.env['nova.forecast.line']
        lines = forecast_line_model.search([
            ('company_id', '=', company_id),
            ('at_risk_excluded', '=', False),
        ] + forecast_line_model._scenario_base_domain())
        category_rows = {}
        for line in lines:
            bucket = line.period_start if granularity == 'week' \
                else forecast_line_model._bucket_month_start(line.expected_date, today)
            key = (line.category_id.id, line.category_id.name or _('Uncategorised'), line.direction)
            row = category_rows.setdefault(key, {})
            bucket_key = fields.Date.to_string(bucket)
            row[bucket_key] = row.get(bucket_key, 0.0) + line.amount_effective

        categories = [{
            'category_id': cat_id,
            'name': name,
            'direction': direction,
            'amounts': amounts,
        } for (cat_id, name, direction), amounts in category_rows.items()]

        return {
            'periods': periods,
            'categories': categories,
            'currency_id': self.env.company.currency_id.id,
        }

    @api.model
    def get_cockpit_drill(self, period_start, granularity, category_id=None, direction=None):
        period_start_date = fields.Date.from_string(period_start)
        today = fields.Date.context_today(self)
        forecast_line_model = self.env['nova.forecast.line']

        domain = [('company_id', '=', self.env.company.id), ('at_risk_excluded', '=', False)]
        domain += forecast_line_model._scenario_base_domain()
        if granularity == 'week':
            domain.append(('period_start', '=', period_start_date))
        if category_id:
            domain.append(('category_id', '=', category_id))
        if direction:
            domain.append(('direction', '=', direction))

        lines = forecast_line_model.search(domain)
        if granularity == 'month':
            lines = lines.filtered(
                lambda l: forecast_line_model._bucket_month_start(l.expected_date, today) == period_start_date
            )

        return {
            'currency_id': self.env.company.currency_id.id,
            'lines': [{
                'id': line.id,
                'partner': line.partner_id.display_name or '',
                'category': line.category_id.name or _('Uncategorised'),
                'source_type': line.source_type,
                'expected_date': fields.Date.to_string(line.expected_date),
                'amount': line.amount_effective,
                'direction': line.direction,
                'move_info_id': line.move_info_id.id or False,
            } for line in lines],
        }
