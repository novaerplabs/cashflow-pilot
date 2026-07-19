from datetime import timedelta

from odoo import api, fields, models, _


class NovaReadinessIssue(models.Model):
    _name = 'nova.readiness.issue'
    _description = 'Cash Flow Data Readiness Issue'
    _order = 'severity desc, issue_type'

    issue_type = fields.Selection([
        ('no_due_date', 'Posted moves without a due date'),
        ('stale_journal', 'Journal with no recent posted entry'),
        ('missing_rate', 'Foreign-currency exposure with a stale rate'),
        ('draft_backlog', 'Draft invoices/bills older than 7 days'),
    ], required=True, index=True)
    severity = fields.Selection([('info', 'Info'), ('warning', 'Warning')], required=True)
    record_count = fields.Integer()
    description = fields.Char()
    company_id = fields.Many2one('res.company', required=True, index=True)
    last_checked = fields.Datetime()

    def action_view_records(self):
        self.ensure_one()
        domain, res_model = self._get_records_domain()
        return {
            'type': 'ir.actions.act_window',
            'name': self.description,
            'res_model': res_model,
            'view_mode': 'list,form',
            'domain': domain,
        }

    def _get_records_domain(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.issue_type == 'no_due_date':
            return [
                ('state', '=', 'posted'),
                ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
                ('amount_residual', '!=', 0),
                ('invoice_date_due', '=', False),
                ('company_id', '=', self.company_id.id),
            ], 'account.move'
        if self.issue_type == 'stale_journal':
            stale_journals = self._find_stale_journals(self.company_id, today)
            return [('id', 'in', stale_journals.ids)], 'account.journal'
        if self.issue_type == 'missing_rate':
            stale_currencies = self._find_stale_currencies(self.company_id, today)
            return [('id', 'in', stale_currencies.ids)], 'res.currency'
        if self.issue_type == 'draft_backlog':
            return [
                ('state', '=', 'draft'),
                ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
                ('invoice_date', '<=', today - timedelta(days=7)),
                ('company_id', '=', self.company_id.id),
            ], 'account.move'
        return [], 'account.move'

    def _find_stale_journals(self, company, today):
        cutoff = today - timedelta(days=30)
        stale = self.env['account.journal']
        for journal in company.nova_journal_ids:
            recent = self.env['account.move.line'].sudo().search_count([
                ('journal_id', '=', journal.id),
                ('move_id.state', '=', 'posted'),
                ('date', '>=', cutoff),
            ])
            if not recent:
                stale |= journal
        return stale

    def _find_stale_currencies(self, company, today):
        cutoff = today - timedelta(days=7)
        infos = self.env['nova.move.info'].sudo().search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ])
        foreign_currencies = infos.mapped('move_id.currency_id').filtered(lambda c: c != company.currency_id)
        stale = self.env['res.currency']
        for currency in foreign_currencies:
            recent_rate = self.env['res.currency.rate'].sudo().search_count([
                ('currency_id', '=', currency.id),
                ('company_id', '=', company.id),
                ('name', '>=', cutoff),
            ])
            if not recent_rate:
                stale |= currency
        return stale

    def _run_check(self, company):
        """BR-21 (a)-(d), rebuilt fresh on every check."""
        self_sudo = self.sudo()
        self_sudo.search([('company_id', '=', company.id)]).unlink()
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        vals_list = []

        no_due_date_moves = self.env['account.move'].sudo().search([
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
            ('amount_residual', '!=', 0),
            ('invoice_date_due', '=', False),
        ])
        if no_due_date_moves:
            vals_list.append({
                'issue_type': 'no_due_date', 'severity': 'warning',
                'record_count': len(no_due_date_moves),
                'description': _(
                    "%(count)s posted document(s) with an outstanding balance have no due date.",
                    count=len(no_due_date_moves),
                ),
                'company_id': company.id, 'last_checked': now,
            })

        stale_journals = self._find_stale_journals(company, today)
        if stale_journals:
            vals_list.append({
                'issue_type': 'stale_journal', 'severity': 'warning',
                'record_count': len(stale_journals),
                'description': _(
                    "%(count)s selected journal(s) have no posted entry in the last 30 days.",
                    count=len(stale_journals),
                ),
                'company_id': company.id, 'last_checked': now,
            })

        stale_currencies = self._find_stale_currencies(company, today)
        if stale_currencies:
            vals_list.append({
                'issue_type': 'missing_rate', 'severity': 'warning',
                'record_count': len(stale_currencies),
                'description': _(
                    "%(count)s foreign currency(ies) with open balances have no exchange rate "
                    "in the last 7 days.", count=len(stale_currencies),
                ),
                'company_id': company.id, 'last_checked': now,
            })

        draft_moves = self.env['account.move'].sudo().search([
            ('company_id', '=', company.id),
            ('state', '=', 'draft'),
            ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
            ('invoice_date', '<=', today - timedelta(days=7)),
        ])
        if draft_moves:
            vals_list.append({
                'issue_type': 'draft_backlog', 'severity': 'info',
                'record_count': len(draft_moves),
                'description': _(
                    "%(count)s draft invoice(s)/bill(s) are older than 7 days.",
                    count=len(draft_moves),
                ),
                'company_id': company.id, 'last_checked': now,
            })

        if vals_list:
            self_sudo.create(vals_list)
        return True

    @api.model
    def _cron_readiness_check(self):
        for company in self.env['res.company'].search([]):
            self._run_check(company)

    def action_run_check(self):
        company = self.env.company
        self._run_check(company)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Data Readiness Check'),
            'res_model': 'nova.readiness.issue',
            'view_mode': 'list',
            'domain': [('company_id', '=', company.id)],
        }

    @api.model
    def get_cockpit_issues(self):
        issues = self.search([('company_id', '=', self.env.company.id)])
        return [{
            'id': issue.id,
            'severity': issue.severity,
            'description': issue.description,
            'record_count': issue.record_count,
        } for issue in issues]
