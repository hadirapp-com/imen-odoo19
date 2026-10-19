from odoo import _, api, models


class HprFinancialReport(models.TransientModel):
    """Virtual model used by ir_actions_report to build the QWeb PDF context."""

    _name = 'report.hadir_account_reports.report_hpr'
    _description = 'Financial Report (PDF Rendering)'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        report = self.env['account.report'].browse(data.get('report_id') or 0)
        if not report.exists():
            return {}
        options = report._hpr_build_options(dict(data.get('options') or {}))
        table = report._hpr_get_table(options)

        consolidation_label = False
        if options.get('hadir_consolidation'):
            group = self.env.company.hadir_consolidation_company_ids
            suffix = (_("dengan eliminasi antar-cabang")
                      if options.get('hadir_elimination')
                      else _("tanpa eliminasi antar-cabang"))
            consolidation_label = _(
                "Konsolidasi: %s (%s)",
                ' + '.join(group.mapped('display_name')), suffix)

        periods = []
        columns = []
        for column in table['columns']:
            if not periods or periods[-1]['label'] != column['period_label']:
                periods.append({'label': column['period_label'], 'colspan': 0})
            periods[-1]['colspan'] += 1
            columns.append({'name': column['name']})

        lines = [{
            'name': line['name'],
            'level': line['level'],
            'style': 'title' if 'hpr-row--title' in line['classes'] else ('total' if 'hpr-row--total' in line['classes'] else ''),
            'cells': [{'formatted': cell['formatted']} for cell in line['cells']],
        } for line in table['lines']]

        return {
            'doc_ids': docids,
            'doc_model': 'account.report',
            'docs': report,
            'report': {'id': report.id, 'name': report.name},
            'consolidation_label': consolidation_label,
            'periods': periods,
            'columns': columns,
            'lines': lines,
        }
