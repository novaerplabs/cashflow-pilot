from odoo import api, fields, models


class NovaMoveInfo(models.Model):
    _name = 'nova.move.info'
    _description = 'Cash Flow Move Info'
    _inherit = ['mail.thread']
    _order = 'effective_date'

    _RESIDUAL_SIGN = {
        'out_invoice': 1,
        'out_refund': -1,
        'in_invoice': -1,
        'in_refund': 1,
    }

    move_id = fields.Many2one(
        'account.move', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(
        related='move_id.company_id', store=True, index=True,
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', store=True, string='Company Currency',
    )
    direction = fields.Selection(
        [('in', 'Inflow'), ('out', 'Outflow')],
        compute='_compute_direction', store=True,
    )
    due_date = fields.Date(
        related='move_id.invoice_date_due', readonly=True,
    )
    expected_date = fields.Date(tracking=True)
    behavior_date = fields.Date(
        help='Filled by CashFlow Pilot Pro only (payment-behavior model).',
    )
    effective_date = fields.Date(
        compute='_compute_effective_date', store=True, index=True,
    )
    at_risk = fields.Boolean(tracking=True)
    exclude_from_forecast = fields.Boolean(tracking=True)
    risk_note = fields.Char()
    category_id = fields.Many2one(
        'nova.category', required=True, check_company=True,
    )
    residual_company = fields.Monetary(
        currency_field='company_currency_id',
        compute='_compute_residual_company', store=True,
    )
    partner_id = fields.Many2one(
        related='move_id.partner_id', store=True, index=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('move_id_uniq', 'unique(move_id)',
         'Only one Cash Flow satellite record is allowed per journal entry.'),
    ]

    @staticmethod
    def _direction_from_move_type(move_type):
        return 'in' if move_type in ('out_invoice', 'out_refund') else 'out'

    @api.depends('move_id.move_type')
    def _compute_direction(self):
        for rec in self:
            rec.direction = rec._direction_from_move_type(rec.move_id.move_type)

    @api.depends(
        'expected_date', 'behavior_date',
        'move_id.invoice_date_due', 'move_id.invoice_date',
        'move_id.partner_id.property_payment_term_id',
    )
    def _compute_effective_date(self):
        for rec in self:
            rec.effective_date = rec._get_effective_date()

    def _get_effective_date(self):
        """BR-01 precedence (Core scope): manual -> due -> BR-02 fallback.

        behavior_date only ever gets populated once CashFlow Pilot Pro is
        installed and its nightly cron writes it (BR-09/BR-10); reading it
        here keeps this method future-proof without requiring Pro.
        """
        self.ensure_one()
        if self.expected_date:
            return self.expected_date
        if self.behavior_date:
            return self.behavior_date
        if self.move_id.invoice_date_due:
            return self.move_id.invoice_date_due
        return self._get_fallback_date()

    def _get_fallback_date(self):
        """BR-02: invoice date + partner payment terms, else invoice date.

        Uses account.payment.term.line._get_due_date(date_ref) per line and
        takes the latest (final installment), rather than account.payment
        .term._compute_terms() - that method also needs tax/currency/sign
        amounts we don't have here and don't need, since BR-02 only wants
        a date, not an amount schedule.
        """
        self.ensure_one()
        move = self.move_id
        base_date = move.invoice_date or fields.Date.context_today(self)
        payment_term = move.partner_id.property_payment_term_id
        if payment_term and payment_term.line_ids:
            due_dates = [line._get_due_date(base_date) for line in payment_term.line_ids]
            if due_dates:
                return max(due_dates)
        return base_date

    @api.depends('move_id.amount_residual', 'move_id.currency_id', 'move_id.company_id', 'move_id.move_type')
    def _compute_residual_company(self):
        today = fields.Date.context_today(self)
        for rec in self:
            move = rec.move_id
            sign = self._RESIDUAL_SIGN.get(move.move_type, 0)
            magnitude = abs(move.amount_residual)
            converted = move.currency_id._convert(magnitude, move.company_id.currency_id, move.company_id, today)
            rec.residual_company = sign * converted

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('category_id') and vals.get('move_id'):
                move = self.env['account.move'].browse(vals['move_id'])
                direction = self._direction_from_move_type(move.move_type)
                category = self.env['nova.category'].search([
                    ('direction', '=', direction),
                    '|', ('company_id', '=', move.company_id.id), ('company_id', '=', False),
                ], limit=1, order='sequence')
                if category:
                    vals['category_id'] = category.id
        return super().create(vals_list)

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
        }

    def action_export_xlsx(self):
        """R-02/R-03: Expected Receipts/Payments schedule export. Exports
        the current selection, or - if nothing is selected - every record
        this user can currently see (record rules/ACL apply as normal).
        """
        records = self if self else self.search([])
        return {
            'type': 'ir.actions.act_url',
            'url': '/cashflow_pilot/export/move_info_xlsx?ids=%s' % ','.join(str(i) for i in records.ids),
            'target': 'download',
        }

    def _sync_move_info(self, companies=None):
        """Lifecycle sync, called by the engine (res.company.action_refresh_forecast,
        P2) at the start of every rebuild. Creates satellites for posted,
        residual-carrying customer/vendor moves and archives satellites
        whose move has settled or left the eligible set. Never writes to
        account.move (HR-1/BR-18).
        """
        move_model = self.env['account.move'].sudo()
        self_sudo = self.sudo()
        companies = companies or self.env['res.company'].sudo().search([])
        moves = move_model.search([
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
            ('company_id', 'in', companies.ids),
            ('amount_residual', '!=', 0),
        ])
        existing = self_sudo.search([('company_id', 'in', companies.ids)])
        existing_by_move = {rec.move_id.id: rec for rec in existing}

        to_create = []
        touched_ids = set()
        for move in moves:
            rec = existing_by_move.get(move.id)
            if rec:
                touched_ids.add(rec.id)
                if not rec.active:
                    rec.active = True
            else:
                to_create.append({'move_id': move.id})

        for i in range(0, len(to_create), 1000):
            self_sudo.create(to_create[i:i + 1000])

        stale = existing.filtered(lambda r: r.id not in touched_ids and r.active)
        if stale:
            stale.write({'active': False})
        return True

    def action_targeted_recompute(self):
        """FR-VIEW-05 / §16 targeted recompute: called after an inline
        expected-date edit. Re-buckets only the forecast lines generated
        from these move.info records, then refreshes period-report rows
        by re-aggregating already-computed forecast lines - skips
        re-deriving lines from source documents, which is the expensive
        part of a full engine rebuild.
        """
        companies = self.mapped('company_id')
        forecast_line = self.env['nova.forecast.line'].sudo()
        forecast_line.search([('move_info_id', 'in', self.ids)]).unlink()
        vals_list = []
        for info in self:
            vals_list += forecast_line._build_move_info_lines(info.company_id, move_infos=info)
        if vals_list:
            forecast_line.create(vals_list)
        self.env['nova.period.report'].sudo()._rebuild(companies)
        return True

    def set_expected_date(self, expected_date):
        """Cockpit DrillDialog inline-edit entry point (FR-VIEW-05). Not
        sudo()'d: goes through the normal ACL/record-rule for this record,
        exactly like editing the field from the form view would.
        """
        self.ensure_one()
        self.expected_date = expected_date
        self.action_targeted_recompute()
        return True
