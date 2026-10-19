import base64
import io

import xlsxwriter

from odoo import http
from odoo.http import request


class HadirAccountReportExportController(http.Controller):

    @http.route('/hadir_account_reports/export/xlsx', type='jsonrpc', auth='user')
    def export_xlsx(self, **kwargs):
        options = kwargs.get('options') or {}
        report = request.env['account.report'].browse(options.get('report_id'))
        if not report.exists():
            return {'error': 'Report not found'}

        table = report._hpr_get_table(report._hpr_build_options(dict(options)))
        report_name = report.name

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(report_name[:31])

        bold = workbook.add_format({'bold': True})
        title = workbook.add_format({'bold': True, 'font_size': 14})
        amount = workbook.add_format({'num_format': '#,##0.00'})
        amount_bold = workbook.add_format({'num_format': '#,##0.00', 'bold': True})

        row_idx = 0
        sheet.write(row_idx, 0, report_name, title)
        row_idx += 2

        # Period header row + column header row
        period_cols = {}
        col_idx = 1
        for column in table['columns']:
            p_idx = column['period_index']
            if p_idx not in period_cols:
                period_cols[p_idx] = {'label': column['period_label'], 'start': col_idx, 'span': 0}
            period_cols[p_idx]['span'] += 1
            sheet.write(row_idx + 1, col_idx, column['name'], bold)
            col_idx += 1
        for info in period_cols.values():
            if info['span'] > 1:
                sheet.merge_range(row_idx, info['start'], row_idx, info['start'] + info['span'] - 1,
                                  info['label'], bold)
            else:
                sheet.write(row_idx, info['start'], info['label'], bold)
        row_idx += 2

        for line in table['lines']:
            style = ('total' if 'hpr-row--total' in line['classes']
                     else 'title' if 'hpr-row--title' in line['classes'] else '')
            name_format = bold if style else None
            cell_format = amount_bold if style == 'total' else amount
            sheet.write(row_idx, 0, '    ' * line['level'] + line['name'], name_format)
            col_idx = 1
            for cell in line['cells']:
                value = cell['value'] if isinstance(cell['value'], (int, float)) else 0.0
                sheet.write_number(row_idx, col_idx, value, cell_format)
                col_idx += 1
            row_idx += 1

        sheet.set_column(0, 0, 48)
        if table['columns']:
            sheet.set_column(1, len(table['columns']), 16)
        workbook.close()
        xlsx_data = output.getvalue()

        filename = f'{report_name}.xlsx'
        return {
            'file_name': filename,
            'file_base64': base64.b64encode(xlsx_data).decode(),
        }
