import io

from odoo.http import Controller, request, route, content_disposition


class NovaXlsxExportController(Controller):
    """R-01/R-02/R-03/R-04 Excel exports. ir.actions.report dropped its
    'xlsx' report_type in this Odoo build, so exports are served via plain
    HTTP controllers that stream an xlsxwriter workbook, matching the
    pattern used elsewhere in core (e.g. product's pricelist export).
    Reads use request.env (the logged-in user's own session) - never
    sudo() - so ACL and multi-company record rules apply exactly as they
    would in any other view.
    """

    def _new_workbook(self):
        buffer = io.BytesIO()
        import xlsxwriter  # noqa: PLC0415
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        return buffer, workbook

    def _xlsx_response(self, buffer, workbook, filename):
        workbook.close()
        content = buffer.getvalue()
        buffer.close()
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename)),
        ]
        return request.make_response(content, headers)

    @route('/cashflow_pilot/export/forecast_xlsx', type='http', auth='user', readonly=True)
    def export_forecast_xlsx(self, granularity='week'):
        """R-01: grid sheet + one combined 'Details' drill sheet (T-02)."""
        company = request.env.company
        reports = request.env['nova.period.report'].search([
            ('company_id', '=', company.id),
            ('granularity', '=', granularity),
        ], order='period_start')
        lines = request.env['nova.forecast.line'].search([
            ('company_id', '=', company.id),
            ('at_risk_excluded', '=', False),
        ], order='period_start')

        buffer, workbook = self._new_workbook()
        bold = workbook.add_format({'bold': True})
        date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd'})

        grid_sheet = workbook.add_worksheet('Grid')
        grid_sheet.write(0, 0, 'Period', bold)
        for col, r in enumerate(reports, start=1):
            grid_sheet.write_datetime(0, col, r.period_start, date_fmt)
        row_labels = [
            ('Opening', 'opening'), ('Inflow', 'inflow'), ('Outflow', 'outflow'),
            ('Net', 'net'), ('Closing', 'closing'),
        ]
        for row_index, (label, field_name) in enumerate(row_labels, start=1):
            grid_sheet.write(row_index, 0, label, bold)
            for col, r in enumerate(reports, start=1):
                grid_sheet.write_number(row_index, col, getattr(r, field_name))
        grid_sheet.set_column(0, 0, 18)
        grid_sheet.set_column(1, len(reports), 14)

        details_sheet = workbook.add_worksheet('Details')
        headers = ['Period', 'Expected Date', 'Partner', 'Category', 'Source', 'Direction', 'Amount']
        for col, header in enumerate(headers):
            details_sheet.write(0, col, header, bold)
        for row, line in enumerate(lines, start=1):
            details_sheet.write_datetime(row, 0, line.period_start, date_fmt)
            details_sheet.write_datetime(row, 1, line.expected_date, date_fmt)
            details_sheet.write(row, 2, line.partner_id.display_name or '')
            details_sheet.write(row, 3, line.category_id.name or '')
            details_sheet.write(row, 4, line.source_type or '')
            details_sheet.write(row, 5, line.direction or '')
            details_sheet.write_number(row, 6, line.amount_effective)
        details_sheet.set_column(0, 1, 14)
        details_sheet.set_column(2, 4, 20)

        return self._xlsx_response(buffer, workbook, 'Cash Flow Forecast.xlsx')

    @route('/cashflow_pilot/export/move_info_xlsx', type='http', auth='user', readonly=True)
    def export_move_info_xlsx(self, ids):
        """R-02/R-03: Expected Receipts / Payments schedules."""
        id_list = [int(i) for i in ids.split(',') if i]
        records = request.env['nova.move.info'].browse(id_list)

        buffer, workbook = self._new_workbook()
        bold = workbook.add_format({'bold': True})
        date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd'})
        sheet = workbook.add_worksheet('Schedule')
        headers = [
            'Partner', 'Document', 'Due Date', 'Expected Date', 'Effective Date',
            'Residual', 'Category', 'Direction', 'At-Risk', 'Excluded',
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)
        for row, rec in enumerate(records, start=1):
            sheet.write(row, 0, rec.partner_id.display_name or '')
            sheet.write(row, 1, rec.move_id.name or '')
            if rec.due_date:
                sheet.write_datetime(row, 2, rec.due_date, date_fmt)
            if rec.expected_date:
                sheet.write_datetime(row, 3, rec.expected_date, date_fmt)
            sheet.write_datetime(row, 4, rec.effective_date, date_fmt)
            sheet.write_number(row, 5, rec.residual_company)
            sheet.write(row, 6, rec.category_id.name or '')
            sheet.write(row, 7, rec.direction or '')
            sheet.write(row, 8, 'Yes' if rec.at_risk else '')
            sheet.write(row, 9, 'Yes' if rec.exclude_from_forecast else '')
        sheet.set_column(0, 0, 24)
        sheet.set_column(1, 1, 16)
        sheet.set_column(2, 4, 14)
        sheet.set_column(6, 6, 18)

        return self._xlsx_response(buffer, workbook, 'Cash Flow Schedule.xlsx')

    @route('/cashflow_pilot/export/recurring_xlsx', type='http', auth='user', readonly=True)
    def export_recurring_xlsx(self, ids):
        """R-04: Recurring Commitments Register."""
        id_list = [int(i) for i in ids.split(',') if i]
        records = request.env['nova.recurring.item'].browse(id_list)

        buffer, workbook = self._new_workbook()
        bold = workbook.add_format({'bold': True})
        date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd'})

        main_sheet = workbook.add_worksheet('Recurring Items')
        headers = [
            'Name', 'Direction', 'Category', 'Amount (Today)', 'Frequency',
            'Next Occurrences', 'State', 'Start Date', 'End Date',
        ]
        for col, header in enumerate(headers):
            main_sheet.write(0, col, header, bold)
        for row, rec in enumerate(records, start=1):
            main_sheet.write(row, 0, rec.name or '')
            main_sheet.write(row, 1, rec.direction or '')
            main_sheet.write(row, 2, rec.category_id.name or '')
            main_sheet.write_number(row, 3, rec.amount_today)
            main_sheet.write(row, 4, rec.frequency or '')
            main_sheet.write(row, 5, rec.next_occurrences or '')
            main_sheet.write(row, 6, rec.state or '')
            if rec.start_date:
                main_sheet.write_datetime(row, 7, rec.start_date, date_fmt)
            if rec.end_date:
                main_sheet.write_datetime(row, 8, rec.end_date, date_fmt)
        main_sheet.set_column(0, 0, 24)
        main_sheet.set_column(2, 2, 18)
        main_sheet.set_column(5, 5, 30)

        revision_sheet = workbook.add_worksheet('Revision History')
        rev_headers = ['Recurring Item', 'Effective From', 'Amount']
        for col, header in enumerate(rev_headers):
            revision_sheet.write(0, col, header, bold)
        row = 1
        for rec in records:
            for revision in rec.revision_ids.sorted('effective_from'):
                revision_sheet.write(row, 0, rec.name or '')
                revision_sheet.write_datetime(row, 1, revision.effective_from, date_fmt)
                revision_sheet.write_number(row, 2, revision.amount)
                row += 1
        revision_sheet.set_column(0, 0, 24)
        revision_sheet.set_column(1, 1, 14)

        return self._xlsx_response(buffer, workbook, 'Recurring Commitments Register.xlsx')
