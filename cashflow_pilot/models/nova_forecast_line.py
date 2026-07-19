from datetime import timedelta

from odoo import api, fields, models


class NovaForecastLine(models.Model):
    _name = 'nova.forecast.line'
    _description = 'Cash Flow Forecast Line'
    _order = 'expected_date'
    _rec_name = 'expected_date'

    _WEEKDAY_MAP = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
    _SOURCE_TYPE_MAP = {
        'out_invoice': 'invoice',
        'out_refund': 'refund_in',
        'in_invoice': 'bill',
        'in_refund': 'refund_out',
    }

    company_id = fields.Many2one('res.company', required=True, index=True)
    source_type = fields.Selection([
        ('invoice', 'Customer Invoice'),
        ('refund_in', 'Customer Credit Note'),
        ('bill', 'Vendor Bill'),
        ('refund_out', 'Vendor Credit Note'),
        ('recurring', 'Recurring Item'),
        ('manual', 'Manual Item'),
        ('pipeline_so', 'Sales Pipeline'),
        ('pipeline_po', 'Purchase Pipeline'),
    ], required=True, index=True)
    move_info_id = fields.Many2one('nova.move.info', index=True)
    recurring_item_id = fields.Many2one('nova.recurring.item', index=True)
    manual_item_id = fields.Many2one('nova.manual.item', index=True)
    partner_id = fields.Many2one('res.partner')
    category_id = fields.Many2one('nova.category', index=True)
    direction = fields.Selection([('in', 'Inflow'), ('out', 'Outflow')], required=True)
    expected_date = fields.Date(required=True, index=True)
    period_start = fields.Date(required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, string='Company Currency')
    amount_company = fields.Monetary(required=True, currency_field='currency_id')
    probability = fields.Float(default=1.0)
    amount_effective = fields.Monetary(
        compute='_compute_amount_effective', store=True, currency_field='currency_id',
    )
    at_risk_excluded = fields.Boolean()

    _sql_constraints = [
        ('probability_range', 'CHECK(probability >= 0 AND probability <= 1)',
         'Probability must be between 0 and 1.'),
    ]

    @api.depends('amount_company', 'probability')
    def _compute_amount_effective(self):
        for rec in self:
            rec.amount_effective = rec.amount_company * rec.probability

    @api.model
    def _bucket_week_start(self, effective_date, week_start_day, today=None):
        """BR-04: week bucket = week-start day of the effective date; dates
        before today land in the current (today's) period, never dropped.
        """
        today = today or fields.Date.context_today(self)
        anchor = max(effective_date, today)
        target = self._WEEKDAY_MAP.get(week_start_day, 0)
        delta = (anchor.weekday() - target) % 7
        return anchor - timedelta(days=delta)

    @api.model
    def _bucket_month_start(self, expected_date, today=None):
        """Same never-dropped clamp as _bucket_week_start, at month grain -
        used both by the monthly period-report pass and the cockpit grid."""
        today = today or fields.Date.context_today(self)
        anchor = max(expected_date, today)
        return anchor.replace(day=1)

    @api.model
    def _scenario_base_domain(self):
        """Forward-compatible guard (AD-03): once Pro adds scenario_id,
        base rebuilds/queries must only touch scenario_id=False lines, so
        scenario-tagged lines never leak into or get wiped by the live
        forecast. Introspects rather than depending on Pro, so this works
        whether or not Pro is installed.
        """
        return [('scenario_id', '=', False)] if 'scenario_id' in self._fields else []

    def _rebuild(self, companies):
        """BR-17: delete + rebuild per company, in one transaction."""
        self_sudo = self.sudo()
        existing = self_sudo.search([('company_id', 'in', companies.ids)] + self._scenario_base_domain())
        if existing:
            existing.unlink()
        vals_list = []
        for company in companies:
            vals_list += self_sudo._build_move_info_lines(company)
            vals_list += self_sudo._build_recurring_lines(company)
            vals_list += self_sudo._build_manual_lines(company)
            vals_list += self_sudo._build_bridge_lines(company)
        for i in range(0, len(vals_list), 1000):
            self_sudo.create(vals_list[i:i + 1000])
        return True

    def _build_bridge_lines(self, company):
        """Forward-compatible extension point (mirrors _scenario_base_domain,
        AD-03): a no-op here so the sale/purchase pipeline bridges (P7) can
        contribute pipeline_so/pipeline_po lines into the live rebuild via a
        plain _inherit override of this one hook, without overriding
        _rebuild() itself or any other core engine method.
        """
        return []

    def _build_move_info_lines(self, company, move_infos=None):
        week_start = company.nova_week_start or 'mon'
        today = fields.Date.context_today(self)
        if move_infos is None:
            move_infos = self.env['nova.move.info'].sudo().search([
                ('company_id', '=', company.id),
                ('active', '=', True),
            ])
        vals_list = []
        for info in move_infos:
            vals_list.append({
                'company_id': company.id,
                'source_type': self._SOURCE_TYPE_MAP.get(info.move_id.move_type),
                'move_info_id': info.id,
                'partner_id': info.partner_id.id,
                'category_id': info.category_id.id,
                'direction': info.direction,
                'expected_date': info.effective_date,
                'period_start': self._bucket_week_start(info.effective_date, week_start, today),
                'amount_company': info.residual_company,
                'probability': 1.0,
                'at_risk_excluded': info.exclude_from_forecast,
            })
        return vals_list

    def _build_recurring_lines(self, company):
        week_start = company.nova_week_start or 'mon'
        today = fields.Date.context_today(self)
        horizon_weeks = int(company.nova_horizon or '13')
        horizon_end = today + timedelta(weeks=horizon_weeks)
        items = self.env['nova.recurring.item'].sudo().search([
            ('company_id', '=', company.id),
            ('state', '=', 'active'),
        ])
        vals_list = []
        for item in items:
            for occ_date in item._get_occurrence_dates(today, horizon_end):
                amount = item._get_effective_amount(occ_date)
                company_amount = item.currency_id._convert(amount, company.currency_id, company, today)
                signed = company_amount if item.direction == 'in' else -company_amount
                vals_list.append({
                    'company_id': company.id,
                    'source_type': 'recurring',
                    'recurring_item_id': item.id,
                    'partner_id': item.partner_id.id,
                    'category_id': item.category_id.id,
                    'direction': item.direction,
                    'expected_date': occ_date,
                    'period_start': self._bucket_week_start(occ_date, week_start, today),
                    'amount_company': signed,
                    'probability': 1.0,
                    'at_risk_excluded': False,
                })
        return vals_list

    def _build_manual_lines(self, company):
        week_start = company.nova_week_start or 'mon'
        today = fields.Date.context_today(self)
        items = self.env['nova.manual.item'].sudo().search([
            ('company_id', '=', company.id),
            ('state', '=', 'planned'),
        ])
        vals_list = []
        for item in items:
            company_amount = item.currency_id._convert(item.amount, company.currency_id, company, today)
            signed = company_amount if item.direction == 'in' else -company_amount
            vals_list.append({
                'company_id': company.id,
                'source_type': 'manual',
                'manual_item_id': item.id,
                'partner_id': item.partner_id.id,
                'category_id': item.category_id.id,
                'direction': item.direction,
                'expected_date': item.expected_date,
                'period_start': self._bucket_week_start(item.expected_date, week_start, today),
                'amount_company': signed,
                'probability': 1.0,
                'at_risk_excluded': False,
            })
        return vals_list

    def action_open_source(self):
        self.ensure_one()
        if self.move_info_id:
            return self.move_info_id.action_open_move()
        if self.recurring_item_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'nova.recurring.item',
                'view_mode': 'form',
                'res_id': self.recurring_item_id.id,
            }
        if self.manual_item_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'nova.manual.item',
                'view_mode': 'form',
                'res_id': self.manual_item_id.id,
            }
        return False
