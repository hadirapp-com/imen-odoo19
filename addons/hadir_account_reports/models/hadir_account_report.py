import ast
import re
import types
from collections import defaultdict
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tools import formatLang

AGG_TOKEN_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z0-9_]+)\b')
AGG_FORMULA_RE = re.compile(r'^[\s0-9\.\+\-\*\/\(\)]*(?:[\s0-9\.\+\-\*\/\(\)]|(?:[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_]+))*$')


class AccountReport(models.Model):
    _inherit = 'account.report'

    filter_hadir_consolidation = fields.Boolean(
        string="Consolidation Filter",
        help="Offer the 'Branch Consolidation' option: compute per-company "
             "columns (head office + branches) plus a consolidated total.")
    hpr_dynamic = fields.Selection(
        [('taxes', 'Tax Report'),
         ('partner_statement', 'Customer Statement'),
         ('depreciation', 'Depreciation Schedule')],
        string="Dynamic Table Engine",
        help="Reports whose table is synthesized in Python instead of walked "
             "from static line_ids (taxes: one row per installed tax; "
             "partner_statement: per-partner running balance; depreciation: "
             "asset x month matrix).")

    # -------------------------------------------------------------------------
    # Entry points (OWL client action)
    # -------------------------------------------------------------------------

    @api.model
    def get_report_informations(self, options):
        options = dict(options or {})
        report = self.browse(options.get('report_id') or 0)
        if not report.exists():
            raise UserError(_("No report_id provided in options"))
        options = report._hpr_build_options(options)
        table = report._hpr_get_table(options)
        hq = self.env.company
        consolidation_available = bool(
            report.filter_hadir_consolidation
            and hq.hadir_is_head_office
            and hq.hadir_branch_ids)
        return {
            'options': options,
            'report': {'id': report.id, 'name': report.name, 'dynamic': report.hpr_dynamic or False},
            'currency': hq.currency_id.name,
            'filters': {
                'comparison': report.filter_period_comparison,
                'date_mode': 'as_of' if options.get('date_mode') == 'as_of' else 'range',
                'journals': report.filter_journals,
                'show_draft': report.filter_show_draft,
                'unfold_all': report.filter_unfold_all,
                'partner': report.filter_partner,
                'consolidation': {
                    'available': consolidation_available,
                    'enabled': bool(options.get('hadir_consolidation')),
                    'elimination_enabled': bool(options.get('hadir_elimination')),
                    'company_names': (
                        hq.hadir_consolidation_company_ids.mapped('display_name')
                        if consolidation_available else []),
                },
            },
            'periods': table['periods'],
            'columns': table['columns'],
            'lines': table['lines'],
            'journals': report._hpr_get_journals(options),
            'reports_list': report._hpr_get_reports_list(),
        }

    def _hpr_recompute_option_filters(self, field_names):
        for field in field_names:
            if field in self._fields:
                self._compute_report_option_filter(field)

    @api.model
    def hpr_setup_actions_and_menus(self):
        from odoo.addons.hadir_account_reports.hooks import setup_actions_and_menus
        setup_actions_and_menus(self.env)

    # -------------------------------------------------------------------------
    # Options
    # -------------------------------------------------------------------------

    def _hpr_build_options(self, options):
        self.ensure_one()
        today = Date.context_today(self)

        options.setdefault('report_id', self.id)
        options.setdefault('all_entries', False)
        options.setdefault('unfold_all', False)
        options.setdefault('unfolded_lines', {})
        options.setdefault('journals', [])
        options.setdefault('partners', [])
        options.setdefault('monthly_mode', False)
        comparison = options.setdefault('comparison', {'mode': 'none', 'number': 1})
        comparison.setdefault('mode', 'none')
        comparison.setdefault('number', 1)

        date_filter = options.setdefault('date_filter', {})
        date_from = date_filter.get('date_from')
        date_to = date_filter.get('date_to')
        date_from = Date.to_date(date_from) if date_from else None
        date_to = Date.to_date(date_to) if date_to else None
        if not date_to:
            date_to = today
        if not date_from:
            opening = self.default_opening_date_filter or 'this_year'
            date_from = self._hpr_default_date_from(opening, date_to)
        date_filter['date_from'] = Date.to_string(date_from)
        date_filter['date_to'] = Date.to_string(date_to)

        if self._hpr_is_balance_sheet():
            options['balance_mode'] = True
            options['date_mode'] = 'as_of'
            options['monthly_mode'] = False
            # Every balance-sheet expression is cumulative (date_scope
            # from_beginning), so values depend on date_to only; collapsing
            # date_from onto it yields the EE "As of" single-date semantics.
            date_filter['date_from'] = date_filter['date_to']

        # Consolidation scope is ALWAYS recomputed server-side: the client
        # cannot forge company_ids. Active only for head offices on plain
        # hierarchical reports (no groupby rows — Balance Sheet / P&L).
        wanted = bool(options.get('hadir_consolidation'))
        want_elim = bool(options.get('hadir_elimination'))
        hq = self.env.company
        options['hadir_consolidation'] = False
        options['hadir_scope_company_ids'] = False
        options['hadir_elimination'] = False
        options['hadir_elimination_pairs'] = False
        if ((wanted or want_elim)
                and self.filter_hadir_consolidation
                and hq.hadir_is_head_office
                and hq.hadir_branch_ids
                and not any(l.groupby or l.user_groupby for l in self.line_ids)):
            group = hq.hadir_consolidation_company_ids
            options['hadir_consolidation'] = True
            options['hadir_scope_company_ids'] = group.ids
            if want_elim:
                pairs_domain = self._hpr_elimination_pairs_domain(group)
                if pairs_domain:
                    options['hadir_elimination'] = True
                    options['hadir_elimination_pairs'] = pairs_domain
        return options

    def _hpr_elimination_pairs_domain(self, group):
        """OR-domain matching cross-company legs: AMLs held by company C whose
        partner belongs to another group company D. Built in flattened prefix
        notation — nested ['&', leaf, leaf] sublists are parsed as leaves."""
        terms = []
        partners = {c.id: c.partner_id for c in group}
        for c in group:
            for d in group:
                if c.id == d.id or not partners[d.id]:
                    continue
                terms.append(['&',
                              ('company_id', '=', c.id),
                              ('partner_id', 'child_of', partners[d.id].ids)])
        if not terms:
            return False
        domain = ['|'] * (len(terms) - 1)
        for term in terms:
            domain.extend(term)
        return domain

    def _hpr_fy_dates(self, ref_date):
        """Odoo 19 returns a dict; older versions returned a tuple."""
        result = self.env.company.compute_fiscalyear_dates(ref_date)
        if isinstance(result, dict):
            return result['date_from'], result['date_to']
        return result

    def _hpr_default_date_from(self, opening, today):
        if opening == 'today':
            return today
        if opening == 'this_month':
            return today.replace(day=1)
        if opening == 'previous_month':
            first_this = today.replace(day=1)
            return first_this - timedelta(days=1)
        if opening == 'this_quarter':
            return date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
        if opening == 'previous_quarter':
            q_first = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
            return q_first - timedelta(days=92)
        if opening == 'previous_year':
            fy_start, _fy_end = self._hpr_fy_dates(today)
            return fy_start.replace(year=fy_start.year - 1)
        # this_year and fallback
        fy_start, _fy_end = self._hpr_fy_dates(today)
        return fy_start

    def _hpr_is_balance_sheet(self):
        self.ensure_one()
        return bool(
            self.line_ids.expression_ids.filtered(lambda e: e.date_scope == 'from_beginning')
        ) and not bool(self.line_ids.expression_ids.filtered(lambda e: e.date_scope == 'strict_range' and e.engine == 'domain'))

    # -------------------------------------------------------------------------
    # Periods / columns
    # -------------------------------------------------------------------------

    def _hpr_get_periods(self, options):
        date_from = Date.to_date(options['date_filter']['date_from'])
        date_to = Date.to_date(options['date_filter']['date_to'])
        periods = []

        if options.get('monthly_mode'):
            month_start = date(date_from.year, date_from.month, 1)
            while month_start <= date_to:
                month_end = self._hpr_month_end(month_start)
                periods.append({
                    'date_from': month_start,
                    'date_to': min(month_end, date_to),
                    'label': month_start.strftime('%b %Y'),
                })
                month_start = month_end + timedelta(days=1)
        else:
            periods.append({
                'date_from': date_from,
                'date_to': date_to,
                'label': self._hpr_period_label(date_from, date_to),
            })
            mode = options['comparison']['mode']
            number = max(1, int(options['comparison'].get('number') or 1))
            if mode == 'previous_period':
                prev_from, prev_to = date_from, date_to
                for _i in range(number):
                    length = (prev_to - prev_from).days + 1
                    prev_to = prev_from - timedelta(days=1)
                    prev_from = prev_to - timedelta(days=length - 1)
                    periods.append({
                        'date_from': prev_from,
                        'date_to': prev_to,
                        'label': self._hpr_period_label(prev_from, prev_to),
                    })
            elif mode == 'previous_year':
                for i in range(1, number + 1):
                    years_back = 366 * i if self._hpr_crosses_feb29(date_from, date_to) else 365 * i
                    periods.append({
                        'date_from': date_from - timedelta(days=years_back),
                        'date_to': date_to - timedelta(days=years_back),
                        'label': self._hpr_period_label(date_from - timedelta(days=years_back),
                                                        date_to - timedelta(days=years_back)),
                    })
        return periods

    def _hpr_month_end(self, month_start):
        if month_start.month == 12:
            return date(month_start.year, 12, 31)
        return date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

    def _hpr_crosses_feb29(self, date_from, date_to):
        for year in (date_from.year, date_to.year):
            try:
                date(year, 2, 29)
                if date_from <= date(year, 2, 29) <= date_to:
                    return True
            except ValueError:
                pass
        return False

    def _hpr_period_label(self, date_from, date_to):
        if self._hpr_is_balance_sheet():
            return _('As of %s', date_to.strftime('%b %d, %Y'))
        if date_from == date_to:
            return date_from.strftime('%b %d, %Y')
        return _('%(start)s to %(end)s',
                 start=date_from.strftime('%b %d, %Y'),
                 end=date_to.strftime('%b %d, %Y'))

    # -------------------------------------------------------------------------
    # Table
    # -------------------------------------------------------------------------

    def _hpr_get_table(self, options):
        self.ensure_one()
        if options.get('hadir_consolidation'):
            return self._hpr_get_consolidated_table(options)
        if self.hpr_dynamic == 'taxes':
            return self._hpr_get_tax_table(options)
        if self.hpr_dynamic == 'partner_statement':
            return self._hpr_get_partner_statement_table(options)
        if self.hpr_dynamic == 'depreciation':
            return self._hpr_get_depreciation_table(options)
        periods = self._hpr_get_periods(options)
        columns = []
        for p_idx, period in enumerate(periods):
            for col in self.column_ids.sorted('sequence'):
                columns.append({
                    'expression_label': col.expression_label,
                    'period_index': p_idx,
                    'period_label': period['label'],
                    'name': col.name,
                    'figure_type': col.figure_type or 'monetary',
                    'blank_if_zero': col.blank_if_zero,
                })
        lines = self._hpr_get_lines(periods, options)
        return {
            'periods': [{'label': p['label']} for p in periods],
            'columns': columns,
            'lines': lines,
        }

    def _hpr_get_consolidated_table(self, options):
        """One column block per company (head office first, branches next),
        optionally an intercompany-elimination block, plus a final
        consolidated-total block. Rows are computed once per scope with the
        standard engine, then merged by row id."""
        self.ensure_one()
        group = self.env.company.hadir_consolidation_company_ids
        # env.company follows the FIRST allowed company: keep head office first
        self = self.with_context(allowed_company_ids=group.ids)
        periods = self._hpr_get_periods(options)
        report_cols = self.column_ids.sorted('sequence')
        block_size = len(periods) * len(report_cols)
        eliminating = bool(options.get('hadir_elimination'))
        currency = self.env.company.currency_id

        scopes = list(group)
        scope_labels = [c.display_name for c in group]
        if eliminating:
            scopes.append('elim')
            scope_labels.append(_('Eliminasi Antar-Cabang'))
        scopes.append('total')
        scope_labels.append(_('Total Konsolidasi'))

        # unique running period_index so PDF/XLSX header blocks never collide
        columns = []
        col_index = 0
        for scope, label in zip(scopes, scope_labels):
            for period in periods:
                for col in report_cols:
                    columns.append({
                        'expression_label': col.expression_label,
                        'period_index': col_index,
                        'period_label': label,
                        'name': period['label'],
                        'figure_type': col.figure_type or 'monetary',
                        'blank_if_zero': col.blank_if_zero,
                    })
                    col_index += 1

        def run_scope(scope):
            scoped = dict(options)
            scoped['hadir_elimination_pairs'] = (
                options['hadir_elimination_pairs'] if scope == 'elim' else False)
            scoped['hadir_scope_company_ids'] = (
                [scope.id] if not isinstance(scope, str) else group.ids)
            return {row['id']: row for row in self._hpr_get_lines(periods, scoped)}

        company_keys = [c.id for c in group]
        runs = {}
        for scope in scopes:
            key = scope if isinstance(scope, str) else scope.id
            runs[key] = run_scope(scope)

        # canonical order: total run, then companies, then elimination-only rows
        row_ids = []
        for rows_map in [runs['total']] + [runs[k] for k in company_keys] + (
                [runs['elim']] if eliminating else []):
            for rid in rows_map:
                if rid not in row_ids:
                    row_ids.append(rid)

        empty_cell = {'value': 0.0, 'formatted': '', 'plain': '',
                      'figure_type': 'monetary', 'classes': ''}
        lines = []
        for rid in row_ids:
            source = (runs['total'].get(rid)
                      or next((runs[k][rid] for k in company_keys if rid in runs[k]), None)
                      or (runs.get('elim', {}).get(rid)))
            row = dict(source)
            elim_row = runs.get('elim', {}).get(rid) if eliminating else None
            cells = []
            # per-company blocks: copied verbatim
            for key in company_keys:
                src_row = runs[key].get(rid)
                for cell_idx in range(block_size):
                    cells.append(dict(
                        src_row['cells'][cell_idx] if src_row is not None else empty_cell))
            # elimination block: negated intercompany legs
            if eliminating:
                for cell_idx in range(block_size):
                    raw = elim_row['cells'][cell_idx]['value'] if elim_row else 0.0
                    cells.append(self._hpr_format_cell(
                        -raw, report_cols[cell_idx % len(report_cols)], currency))
            # total block: companies + elimination (net of intercompany)
            total_row = runs['total'].get(rid)
            for cell_idx in range(block_size):
                value = total_row['cells'][cell_idx]['value'] if total_row else 0.0
                if eliminating:
                    value -= elim_row['cells'][cell_idx]['value'] if elim_row else 0.0
                cells.append(self._hpr_format_cell(
                    value, report_cols[cell_idx % len(report_cols)], currency))
            row['cells'] = cells
            lines.append(row)
        return {
            'periods': [{'label': label} for label in scope_labels],
            'columns': columns,
            'lines': lines,
        }

    def _hpr_get_tax_table(self, options):
        """Dynamic Tax Report: one row per top-level installed tax (company,
        active), grouped Output (sale) / Input (purchase). Base = base lines
        carrying the tax in tax_ids; Tax = repartition lines posting to it
        (tax_line_id). Group taxes roll their children in. Both columns show
        positive amounts for normal operations; credit notes net out."""
        self.ensure_one()
        periods = self._hpr_get_periods(options)
        report_cols = self.column_ids.sorted('sequence')
        columns = []
        for p_idx, period in enumerate(periods):
            for col in report_cols:
                columns.append({
                    'expression_label': col.expression_label,
                    'period_index': p_idx,
                    'period_label': period['label'],
                    'name': col.name,
                    'figure_type': col.figure_type or 'monetary',
                    'blank_if_zero': col.blank_if_zero,
                })
        currency = self.env.company.currency_id
        base_col = report_cols.filtered(lambda c: c.expression_label == 'base')[:1]
        tax_col = report_cols.filtered(lambda c: c.expression_label == 'tax')[:1]
        if not base_col or not tax_col:
            base_col = tax_col = report_cols[:1]

        def title_cells():
            return [{
                'value': 0.0, 'formatted': '', 'plain': '',
                'figure_type': col.figure_type or 'monetary', 'classes': '',
            } for col in report_cols for _period in periods]

        def tax_values(tax, scope_sign, period):
            # NOTE: v19 has no per-line cash-basis exigibility flag; l10n_id
            # taxes are invoice-basis so the date range filter is exact.
            related = (tax | tax.children_tax_ids)
            base_domain = [('tax_ids', 'in', related.ids), ('tax_line_id', '=', False)]
            tax_domain = [('tax_line_id', 'in', related.ids)]
            base_val = tax_val = 0.0
            for domain, out in ((base_domain, 'base'), (tax_domain, 'tax')):
                scoped = self._hpr_apply_date_scope(list(domain), 'strict_range', period)
                scoped = self._hpr_apply_base_filters(scoped, options)
                balance = self._hpr_aml_aggregates(scoped)['balance']
                if out == 'base':
                    base_val = scope_sign * balance
                else:
                    tax_val = scope_sign * balance
            return base_val, tax_val

        def values_row(row_id, name, level, classes, base_vals, tax_vals):
            cells = []
            for p_idx in range(len(periods)):
                cells.append(self._hpr_format_cell(base_vals[p_idx], base_col, currency))
                cells.append(self._hpr_format_cell(tax_vals[p_idx], tax_col, currency))
            return {
                'id': row_id, 'name': name, 'level': level, 'classes': classes,
                'foldable': False, 'unfolded': False, 'cells': cells,
                'action_id': 0, 'has_more': False, 'groupby': False,
            }

        lines = []
        grand_base = [0.0] * len(periods)
        grand_tax = [0.0] * len(periods)
        for scope, title, scope_sign in (
                ('sale', _('Output Tax (Sales)'), -1.0),
                ('purchase', _('Input Tax (Purchases)'), 1.0)):
            taxes = self.env['account.tax'].search([
                ('company_id', 'in',
                 options.get('hadir_scope_company_ids') or self.env.companies.ids),
                ('type_tax_use', '=', scope),
            ], order='sequence, name')
            child_ids = set(taxes.children_tax_ids.ids)
            taxes = taxes.filtered(lambda t: t.id not in child_ids)
            section_rows = []
            sec_base = [0.0] * len(periods)
            sec_tax = [0.0] * len(periods)
            for tax in taxes:
                row_base = [0.0] * len(periods)
                row_tax = [0.0] * len(periods)
                for p_idx, period in enumerate(periods):
                    row_base[p_idx], row_tax[p_idx] = tax_values(tax, scope_sign, period)
                if not any(row_base) and not any(row_tax):
                    continue
                sec_base = [a + b for a, b in zip(sec_base, row_base)]
                sec_tax = [a + b for a, b in zip(sec_tax, row_tax)]
                section_rows.append(values_row(
                    f'tax_{tax.id}', tax.name, 1, [], row_base, row_tax))
            if not section_rows:
                continue
            unfold_key = f'tax_scope_{scope}'
            unfolded = bool(options.get('unfold_all')
                            or options['unfolded_lines'].get(unfold_key))
            lines.append({
                'id': unfold_key, 'name': title, 'level': 0,
                'classes': ['hpr-row--title'], 'foldable': True,
                'unfolded': unfolded, 'cells': title_cells(),
                'action_id': 0, 'has_more': False, 'groupby': False,
            })
            if unfolded:
                lines.extend(section_rows)
            lines.append(values_row(
                f'total_tax_{scope}', _('Subtotal %s', title), 1,
                ['hpr-row--total'], sec_base, sec_tax))
            grand_base = [a + b for a, b in zip(grand_base, sec_base)]
            grand_tax = [a + b for a, b in zip(grand_tax, sec_tax)]
        if any(grand_base) or any(grand_tax):
            lines.append(values_row(
                'total_tax_grand', _('Total'), 0,
                ['hpr-row--total'], grand_base, grand_tax))
        return {
            'periods': [{'label': p['label']} for p in periods],
            'columns': columns,
            'lines': lines,
        }

    def _hpr_get_partner_statement_table(self, options):
        """Customer Statement: per-partner running-balance ledger over the
        receivable accounts, for the single selected period (this report has
        comparison/monthly controls disabled). With no partner selection,
        every partner with an opening balance or in-range movement shows up."""
        self.ensure_one()
        periods = self._hpr_get_periods(options)
        report_cols = self.column_ids.sorted('sequence')
        columns = []
        for p_idx, period in enumerate(periods):
            for col in report_cols:
                columns.append({
                    'expression_label': col.expression_label,
                    'period_index': p_idx,
                    'period_label': period['label'],
                    'name': col.name,
                    'figure_type': col.figure_type or 'monetary',
                    'blank_if_zero': col.blank_if_zero,
                })
        currency = self.env.company.currency_id
        col_by_label = {c.expression_label: c for c in report_cols}
        debit_col = col_by_label.get('debit', report_cols[0])
        credit_col = col_by_label.get('credit', report_cols[0])
        balance_col = col_by_label.get('balance', report_cols[0])
        period = periods[0]
        date_from, date_to = period['date_from'], period['date_to']

        aml = self.env['account.move.line']
        base_domain = [('account_type', '=', 'asset_receivable')]

        def scoped(extra):
            return self._hpr_apply_base_filters(list(base_domain) + extra, options)

        def partner_totals(domain):
            totals = {}
            for group in aml._read_group(
                    domain, ['partner_id'],
                    ['balance:sum', 'debit:sum', 'credit:sum']):
                partner = group[0]
                if isinstance(partner, tuple):
                    pid, disp = partner
                else:
                    pid, disp = partner.id, partner.display_name
                if pid:
                    totals[pid] = {'name': disp, 'balance': group[1],
                                   'debit': group[2], 'credit': group[3]}
            return totals

        opening_totals = partner_totals(scoped([('date', '<', date_from)]))
        move_totals = partner_totals(scoped(
            [('date', '>=', date_from), ('date', '<=', date_to)]))
        selected = [int(p) for p in (options.get('partners') or [])]
        if selected:
            pids = [(p.id, p.display_name)
                    for p in self.env['res.partner'].browse(selected).exists()]
        else:
            merged = {**opening_totals, **move_totals}
            pids = sorted(merged.items(), key=lambda kv: kv[1]['name'])
            pids = [(pid, info['name']) for pid, info in pids]

        def cells_from(debit=0.0, credit=0.0, balance=0.0):
            values = {'debit': debit, 'credit': credit, 'balance': balance}
            return [self._hpr_format_cell(values.get(col.expression_label, 0.0), col, currency)
                    for col in report_cols]

        lines = []
        auto_unfold = len(pids) == 1
        for pid, pname in pids:
            opening = opening_totals.get(pid) or {
                'balance': 0.0, 'debit': 0.0, 'credit': 0.0}
            movement = move_totals.get(pid) or {
                'balance': 0.0, 'debit': 0.0, 'credit': 0.0}
            closing_balance = opening['balance'] + movement['balance']
            unfold_key = f'stmt_{pid}'
            unfolded = bool(auto_unfold
                            or options.get('unfold_all')
                            or options['unfolded_lines'].get(unfold_key))
            lines.append({
                'id': unfold_key, 'name': pname, 'level': 0,
                'classes': ['hpr-row--title'], 'foldable': True,
                'unfolded': unfolded,
                'cells': cells_from(balance=closing_balance),
                'action_id': 0, 'has_more': False, 'groupby': False,
            })
            if not unfolded:
                continue
            lines.append({
                'id': f'{unfold_key}_init', 'name': _('Initial Balance'),
                'level': 1, 'classes': [], 'foldable': False, 'unfolded': False,
                'cells': cells_from(balance=opening['balance']),
                'action_id': 0, 'has_more': False, 'groupby': False,
            })
            running = opening['balance']
            records = aml.search(
                scoped([('date', '>=', date_from), ('date', '<=', date_to),
                        ('partner_id', '=', pid)]),
                order='date, id', limit=200)
            for line in records:
                running += line.debit - line.credit
                date_label = Date.to_string(line.date)
                label = line.name or line.ref or ''
                name = f"{date_label}  {line.move_id.name or ''} {label}".strip()
                lines.append({
                    'id': f'{unfold_key}_aml_{line.id}', 'name': name,
                    'level': 1, 'classes': [], 'foldable': False,
                    'unfolded': False,
                    'cells': cells_from(debit=line.debit, credit=line.credit,
                                        balance=running),
                    'action_id': 0, 'has_more': False, 'groupby': False,
                })
            lines.append({
                'id': f'{unfold_key}_close', 'name': _('Closing Balance'),
                'level': 1, 'classes': ['hpr-row--total'], 'foldable': False,
                'unfolded': False,
                'cells': cells_from(debit=movement['debit'],
                                    credit=movement['credit'],
                                    balance=closing_balance),
                'action_id': 0, 'has_more': False, 'groupby': False,
            })
        return {
            'periods': [{'label': p['label']} for p in periods],
            'columns': columns,
            'lines': lines,
        }

    @api.model
    def hpr_search_partners(self, search='', limit=20, selected_ids=None, statement=False):
        """Partner picker feed for the report filters (RPC from JS). Returns
        the matches plus the currently selected partners, so their checkboxes
        keep a label."""
        Partner = self.env['res.partner']
        domain = [('name', 'ilike', search or '')]
        if statement:
            domain += [('customer_rank', '>', 0)]
        result = []
        seen = set()
        candidates = list(Partner.search(domain, limit=limit))
        candidates += Partner.browse(selected_ids or []).exists()
        for partner in candidates:
            if partner.id in seen:
                continue
            seen.add(partner.id)
            result.append({'id': partner.id, 'display_name': partner.display_name})
        return result

    def _hpr_get_depreciation_table(self, options):
        """Depreciation Schedule: one row per fixed asset grouped by its
        asset account. Columns: Original Value | the months of the selected
        range (posted amounts, else the projected board) | Accumulated
        (over the asset's full timeline up to date_to) | Book Value."""
        self.ensure_one()
        periods = self._hpr_get_periods(options)
        period = periods[0]
        date_from, date_to = period['date_from'], period['date_to']

        months = []
        cursor = date(date_from.year, date_from.month, 1)
        last = date(date_to.year, date_to.month, 1)
        while cursor <= last and len(months) < 60:
            months.append(cursor)
            cursor = date(cursor.year + (cursor.month == 12),
                          1 if cursor.month == 12 else cursor.month + 1, 1)
        to_key = date_to.strftime('%Y-%m')

        col_defs = [{
            'expression_label': 'original', 'period_index': 0,
            'period_label': 'Original Value', 'name': 'Original Value',
            'figure_type': 'monetary', 'blank_if_zero': False,
        }]
        for month in months:
            col_defs.append({
                'expression_label': 'monthly', 'period_index': 1,
                'period_label': 'Monthly Depreciation',
                'name': month.strftime('%b %Y'),
                'figure_type': 'monetary', 'blank_if_zero': True,
            })
        col_defs.append({
            'expression_label': 'accumulated', 'period_index': 1,
            'period_label': 'Accumulated', 'name': 'Accumulated',
            'figure_type': 'monetary', 'blank_if_zero': False,
        })
        col_defs.append({
            'expression_label': 'book', 'period_index': 1,
            'period_label': 'Book Value', 'name': 'Book Value',
            'figure_type': 'monetary', 'blank_if_zero': False,
        })
        columns = list(col_defs)
        col_objs = [types.SimpleNamespace(**d) for d in col_defs]
        original_col, monthly_cols, accumulated_col, book_col = (
            col_objs[0], col_objs[1:-2], col_objs[-2], col_objs[-1])
        currency = self.env.company.currency_id

        assets = self.env['account.asset'].search([
            ('company_id', 'in',
             options.get('hadir_scope_company_ids') or self.env.companies.ids),
            ('is_deferred', '=', False),
            ('state', 'in', ('running', 'closed')),
        ], order='acquisition_date, id')

        sections = {}
        for asset in assets:
            sections.setdefault(asset.account_asset_id.id, {
                'account': asset.account_asset_id, 'assets': [],
            })
            sections[asset.account_asset_id.id]['assets'].append(asset)

        def asset_metrics(asset):
            posted = {}
            for move in asset.depreciation_move_ids.filtered(
                    lambda m: m.state == 'posted' and not m.hadir_asset_disposal):
                key = move.date.strftime('%Y-%m')
                posted[key] = posted.get(key, 0.0) + move.amount_total_signed
            projected = {}
            if asset.state != 'closed':
                for entry in asset._compute_depreciation_board():
                    projected[entry['date'].strftime('%Y-%m')] = entry['amount']

            def month_value(key):
                if key in posted:
                    return posted[key]
                return projected.get(key, 0.0)

            accumulated = sum(
                month_value(key)
                for key in set(posted) | set(projected) if key <= to_key)
            return month_value, asset.original_value, accumulated, (
                asset.original_value - accumulated)

        def month_lookup(vals):
            return lambda key: vals[
                next(i for i, m in enumerate(months)
                     if m.strftime('%Y-%m') == key)]

        def cells_from(original, fn_monthly, accumulated, book):
            cells = [self._hpr_format_cell(original, original_col, currency)]
            for i, (m, col) in enumerate(zip(months, monthly_cols)):
                cell = self._hpr_format_cell(fn_monthly(m.strftime('%Y-%m')), col, currency)
                if i % 2 == 1:
                    # EE Depreciation Schedule shades alternating month columns
                    cell['classes'] = (cell['classes'] + ' hpr-cell--alt').strip()
                cells.append(cell)
            cells.append(self._hpr_format_cell(accumulated, accumulated_col, currency))
            cells.append(self._hpr_format_cell(book, book_col, currency))
            return cells

        lines = []
        for account_id, section in sorted(
                sections.items(),
                key=lambda kv: (kv[1]['account'].code or '', kv[1]['account'].name or '')):
            unfold_key = f'depr_acc_{account_id}'
            unfolded = bool(options.get('unfold_all')
                            or options['unfolded_lines'].get(unfold_key))
            account = section['account']
            asset_rows = []
            sec_monthly = [0.0] * len(months)
            sec_original = sec_accumulated = sec_book = 0.0
            for asset in section['assets']:
                fn_monthly, original, accumulated, book = asset_metrics(asset)
                sec_monthly = [s + fn_monthly(m.strftime('%Y-%m'))
                               for s, m in zip(sec_monthly, months)]
                sec_original += original
                sec_accumulated += accumulated
                sec_book += book
                name = f"[{asset.code}] {asset.name}" if asset.code else asset.name
                asset_rows.append({
                    'id': f'depr_asset_{asset.id}', 'name': name, 'level': 1,
                    'classes': [], 'foldable': False, 'unfolded': False,
                    'cells': cells_from(original, fn_monthly, accumulated, book),
                    'action_id': 0, 'has_more': False, 'groupby': False,
                })
            lines.append({
                'id': unfold_key,
                'name': f"{account.code} {account.name}" if account.code else account.name,
                'level': 0, 'classes': ['hpr-row--title'], 'foldable': True,
                'unfolded': unfolded,
                'cells': cells_from(sec_original, month_lookup(sec_monthly),
                                    sec_accumulated, sec_book),
                'action_id': 0, 'has_more': False, 'groupby': False,
            })
            if unfolded:
                lines.extend(asset_rows)
        return {
            'periods': [{'label': p['label']} for p in periods],
            'columns': columns,
            'lines': lines,
        }

    def _hpr_get_lines(self, periods, options):
        self.ensure_one()
        registry = {}       # line.id -> {label: [values per period]}
        rows = []
        self._hpr_walk_lines(self.line_ids.filtered(lambda l: not l.parent_id).sorted('sequence'),
                             periods, options, registry, rows)
        return rows

    def _hpr_walk_lines(self, lines, periods, options, registry, rows):
        for line in lines:
            subtree_rows = self._hpr_walk_line(line, periods, options, registry)
            rows.extend(subtree_rows)

    def _hpr_walk_line(self, line, periods, options, registry):
        # 1. Domain (and other direct) expressions first
        totals = registry.setdefault(line.id, defaultdict(lambda: [0.0] * len(periods)))
        direct_exps = line.expression_ids.filtered(lambda e: e.engine in ('domain', 'account_codes', 'external', 'tax_tags'))
        if direct_exps:
            computed = self._hpr_compute_expression_totals(direct_exps, periods, options)
            for exp_id, values in computed.items():
                exp = self.env['account.report.expression'].browse(exp_id)
                totals[exp.label] = values

        # 2. Children (recursively)
        child_rows = []
        child_lines = line.children_ids.sorted('sequence')
        skip_totals_children = []
        for child in child_lines:
            if (child.code or '').startswith('total_'):
                skip_totals_children.append(child)
                continue
            child_rows.extend(self._hpr_walk_line(child, periods, options, registry))

        # 3. Aggregation expressions (need children / sibling totals)
        agg_exps = line.expression_ids.filtered(lambda e: e.engine == 'aggregation')
        if agg_exps:
            computed = self._hpr_resolve_aggregations(agg_exps, line, periods, registry)
            for exp_id, values in computed.items():
                exp = self.env['account.report.expression'].browse(exp_id)
                totals[exp.label] = values

        # 4. Total lines at the end of the subtree, in sequence order
        for child in skip_totals_children:
            child_rows.extend(self._hpr_walk_line(child, periods, options, registry))

        # 5. Build the row of this line
        currency = self.env.company.currency_id
        is_title = line.hierarchy_level == 0 and not line.expression_ids
        cells = []
        has_values = False
        for p_idx in range(len(periods)):
            for col in self.column_ids.sorted('sequence'):
                label = col.expression_label
                value = totals.get(label, [0.0] * len(periods))[p_idx]
                if value:
                    has_values = True
                if is_title:
                    cells.append({'value': 0.0, 'formatted': '',
                                  'figure_type': col.figure_type or 'monetary', 'classes': ''})
                else:
                    cells.append(self._hpr_format_cell(value, col, currency))

        classes = []
        if is_title:
            classes.append('hpr-row--title')
        elif (line.code or '').startswith('total_'):
            classes.append('hpr-row--total')

        if line.hide_if_zero and not has_values:
            return child_rows

        unfold_key = str(line.id)
        is_foldable = bool(line.foldable or line.groupby)
        unfolded = (options['unfold_all']
                    or options['unfolded_lines'].get(unfold_key)
                    or not line.foldable)

        row = {
            'id': unfold_key,
            'name': line.name,
            'level': line.hierarchy_level,
            'classes': classes,
            'foldable': is_foldable,
            'unfolded': bool(unfolded) if is_foldable else False,
            'cells': cells,
            'action_id': line.action_id.id,
            'has_more': False,
            'groupby': False,
        }
        rows = [row]

        if line.groupby and unfolded:
            group_rows = self._hpr_get_groupby_rows(line, periods, options)
            rows.extend(group_rows)
        elif child_rows and unfolded:
            rows.extend(child_rows)
        return rows

    # -------------------------------------------------------------------------
    # Expression computation
    # -------------------------------------------------------------------------

    def _hpr_compute_expression_totals(self, expressions, periods, options):
        """Compute per-period values for direct engines; returns {exp.id: [values]}."""
        results = {}
        aml = self.env['account.move.line']
        for exp in expressions:
            values = [0.0] * len(periods)
            if exp.engine == 'domain':
                base_domain = ast.literal_eval(exp.formula)
                for p_idx, period in enumerate(periods):
                    domain = self._hpr_apply_date_scope(list(base_domain), exp.date_scope, period, exp=exp)
                    domain = self._hpr_apply_base_filters(domain, options)
                    aggregates = self._hpr_aml_aggregates(domain)
                    values[p_idx] = self._hpr_subformula_value(exp.subformula, aggregates)
            elif exp.engine == 'account_codes':
                codes = [t.lstrip('+-').rstrip('DCd') for t in re.split(r'[,\s]+', exp.formula.strip()) if t]
                domain = ['|'] * (len(codes) - 1) + [('account_id.code', '=like', f'{c}%') for c in codes]
                for p_idx, period in enumerate(periods):
                    scoped = self._hpr_apply_date_scope(list(domain), exp.date_scope, period)
                    scoped = self._hpr_apply_base_filters(scoped, options)
                    aggregates = self._hpr_aml_aggregates(scoped)
                    values[p_idx] = self._hpr_subformula_value('sum', aggregates)
            elif exp.engine == 'external':
                for p_idx, period in enumerate(periods):
                    ext_values = self.env['account.report.external.value'].search([
                        ('target_report_expression_id', '=', exp.id),
                        ('company_id', 'in', options.get('hadir_scope_company_ids') or self.env.companies.ids),
                        ('date', '>=', period['date_from']),
                        ('date', '<=', period['date_to']),
                    ])
                    values[p_idx] = sum(ext_values.mapped('value'))
            elif exp.engine == 'tax_tags':
                values = self._hpr_compute_tax_tags(exp, periods, options)
            results[exp.id] = values
        return results

    def _hpr_compute_tax_tags(self, exp, periods, options):
        """Minimal tax_tags engine: sum the balances of journal items carrying
        the tag named by the formula (e.g. '-01' -> tag '01', negated)."""
        aml = self.env['account.move.line']
        formula = (exp.formula or '').strip()
        sign = -1.0 if formula.startswith('-') else 1.0
        tag_name = formula.lstrip('+-').strip()
        country = self.country_id or self.env.company.account_fiscal_country_id
        tag = self.env['account.account.tag'].search([
            ('applicability', '=', 'taxes'),
            ('country_id', '=', country.id),
            '|', ('name', '=', tag_name), ('tax_report_expression_id', '=', exp.id),
        ], limit=1)
        values = [0.0] * len(periods)
        if not tag:
            return values
        for p_idx, period in enumerate(periods):
            domain = self._hpr_apply_date_scope([('tax_tag_ids', 'in', tag.ids)], exp.date_scope, period, exp=exp)
            domain = self._hpr_apply_base_filters(domain, options)
            if self.only_tax_exigible:
                domain += ['|', ('tax_repartition_line_id', '!=', False),
                           '&', ('tax_line_id', '=', False), ('tax_ids', '=', False)]
            aggregates = self._hpr_aml_aggregates(domain)
            values[p_idx] = sign * self._hpr_subformula_value('sum', aggregates)
        return values

    def _hpr_resolve_aggregations(self, expressions, line, periods, registry):
        results = {}
        for exp in expressions:
            formula = exp.formula.strip()
            values = [0.0] * len(periods)
            if formula == 'sum_children':
                label = exp.label
                values = self._hpr_sum_children(line, label, periods, registry)
            else:
                values = self._hpr_eval_aggregation(formula, periods, registry)
            results[exp.id] = values
        return results

    def _hpr_sum_children(self, line, label, periods, registry):
        totals = [0.0] * len(periods)
        for child in line.children_ids:
            if (child.code or '').startswith('total_'):
                continue
            child_values = registry.get(child.id, {}).get(label)
            if child_values is None and child.children_ids:
                child_values = self._hpr_sum_children(child, label, periods, registry)
            if child_values:
                totals = [t + v for t, v in zip(totals, child_values)]
        return totals

    def _hpr_eval_aggregation(self, formula, periods, registry):
        if not AGG_FORMULA_RE.match(formula):
            return [0.0] * len(periods)
        lines_by_code = {l.code: l.id for l in self.line_ids if l.code}
        unresolved = False

        def repl(match):
            nonlocal unresolved
            code, label = match.group(1), match.group(2)
            line_id = lines_by_code.get(code)
            values = registry.get(line_id, {}).get(label) if line_id else None
            if values is None:
                unresolved = True
                return '0'
            return f'({values[period_index]!r})'

        totals = []
        for period_index in range(len(periods)):
            unresolved = False
            expression = AGG_TOKEN_RE.sub(repl, formula)
            if unresolved:
                totals.append(0.0)
                continue
            try:
                totals.append(float(eval(expression, {'__builtins__': {}}, {})))  # noqa: S307 - sanitized by AGG_FORMULA_RE + token substitution
            except Exception:
                totals.append(0.0)
        return totals

    # -------------------------------------------------------------------------
    # SQL helpers
    # -------------------------------------------------------------------------

    def _hpr_aml_aggregates(self, domain):
        aml = self.env['account.move.line']
        groups = aml._read_group(domain, [], ['balance:sum', 'debit:sum', 'credit:sum', 'amount_residual:sum', '__count'])
        if not groups:
            return {'balance': 0.0, 'debit': 0.0, 'credit': 0.0, 'residual': 0.0, 'count': 0}
        balance, debit, credit, residual, count = groups[0]
        return {
            'balance': balance or 0.0,
            'debit': debit or 0.0,
            'credit': credit or 0.0,
            'residual': residual or 0.0,
            'count': count or 0,
        }

    def _hpr_subformula_value(self, subformula, aggregates):
        sub = (subformula or 'sum').strip()
        if sub in ('sum', 'balance'):
            return aggregates['balance']
        if sub == '-sum':
            return -aggregates['balance']
        if sub == 'debit':
            return aggregates['debit']
        if sub == 'credit':
            return aggregates['credit']
        if sub == 'residual':
            return aggregates.get('residual', 0.0)
        if sub == 'count':
            return aggregates['count']
        if sub == 'sum_if_pos':
            return aggregates['balance'] if aggregates['balance'] > 0 else 0.0
        if sub == 'sum_if_neg':
            return aggregates['balance'] if aggregates['balance'] < 0 else 0.0
        return aggregates['balance']

    def _hpr_apply_date_scope(self, domain, date_scope, period, exp=None):
        date_from = period['date_from']
        date_to = period['date_to']
        if date_scope == 'from_beginning':
            domain += [('date', '<=', date_to)]
        elif date_scope == 'from_fiscalyear':
            fy_start, _fy_end = self._hpr_fy_dates(date_to)
            domain += [('date', '>=', fy_start), ('date', '<=', date_to)]
        elif date_scope == 'to_beginning_of_period':
            domain += [('date', '<', date_from)]
        elif date_scope == 'to_beginning_of_fiscalyear':
            fy_start, _fy_end = self._hpr_fy_dates(date_to)
            domain += [('date', '<', fy_start)]
        elif date_scope == 'aging':
            domain += [('date', '<=', date_to)]
            from_days = exp.hpr_aging_from_days if exp is not None else 0
            to_days = exp.hpr_aging_to_days if exp is not None else 0
            if from_days == 0 and to_days == 0:
                domain += [('date_maturity', '>', date_to)]
            else:
                domain += [('date_maturity', '<=', date_to - timedelta(days=from_days))]
                if to_days < 100000:  # open-ended "older" bucket
                    domain += [('date_maturity', '>', date_to - timedelta(days=to_days + 1))]
        else:  # strict_range
            domain += [('date', '>=', date_from), ('date', '<=', date_to)]
        return domain

    def _hpr_apply_base_filters(self, domain, options):
        domain += [('parent_state', 'in', ['posted', 'draft'] if options.get('all_entries') else ['posted'])]
        domain += [('company_id', 'in', options.get('hadir_scope_company_ids') or self.env.companies.ids)]
        domain += options.get('hadir_elimination_pairs') or []
        if options.get('journals'):
            domain += [('journal_id', 'in', options['journals'])]
        if options.get('partners'):
            domain += [('partner_id', 'in', options['partners'])]
        return domain

    # -------------------------------------------------------------------------
    # Groupby (dynamic) lines
    # -------------------------------------------------------------------------

    @staticmethod
    def _hpr_empty_aggregates():
        return {'balance': 0.0, 'debit': 0.0, 'credit': 0.0, 'residual': 0.0, 'count': 0}

    def _hpr_get_groupby_rows(self, line, periods, options):
        group_field = (line.user_groupby or line.groupby).split(',')[0].strip()
        direct_exps = line.expression_ids.filtered(lambda e: e.engine == 'domain')
        if not direct_exps:
            return []
        exps_by_label = {e.label: e for e in direct_exps}

        # Aggregate per period and per expression label, grouped by the group field
        groups = {}  # group_id -> {'name': str, 'per_period': [{label: aggregates}]}
        aml = self.env['account.move.line']
        for p_idx, period in enumerate(periods):
            for exp in direct_exps:
                base_domain = ast.literal_eval(exp.formula)
                domain = self._hpr_apply_date_scope(list(base_domain), exp.date_scope, period, exp=exp)
                domain = self._hpr_apply_base_filters(domain, options)
                grouped = aml._read_group(domain, [group_field],
                                          ['balance:sum', 'debit:sum', 'credit:sum',
                                           'amount_residual:sum', '__count'])
                for row in grouped:
                    group_val = row[0]
                    if isinstance(group_val, tuple):
                        # older _read_group signature: (id, display_name)
                        group_id, display_name = group_val
                    else:
                        # Odoo 19: grouped many2one values are recordsets
                        group_id = group_val.id
                        display_name = group_val.display_name
                    if not group_id:
                        continue
                    entry = groups.setdefault(group_id, {'name': display_name, 'per_period': [None] * len(periods)})
                    per_period = entry['per_period'][p_idx]
                    if per_period is None:
                        per_period = entry['per_period'][p_idx] = {}
                    agg = per_period.setdefault(exp.label, self._hpr_empty_aggregates())
                    balance, debit, credit, residual, count = row[1], row[2], row[3], row[4], row[5]
                    agg['balance'] += balance or 0.0
                    agg['debit'] += debit or 0.0
                    agg['credit'] += credit or 0.0
                    agg['residual'] += residual or 0.0
                    agg['count'] += count or 0

        # Sort: accounts by code, others by name
        group_ids = list(groups.keys())
        if group_field == 'account_id':
            records = self.env['account.account'].browse(group_ids).sorted('code')
            for account in records:
                groups[account.id]['name'] = f'{account.code} {account.name}'
            ordered_ids = records.ids
        elif group_field == 'partner_id':
            records = self.env['res.partner'].browse(group_ids).sorted('name')
            ordered_ids = records.ids
        else:
            ordered_ids = sorted(group_ids, key=lambda gid: groups[gid]['name'] or '')

        currency = self.env.company.currency_id
        is_aging = any(e.date_scope == 'aging' for e in direct_exps)
        rows = []
        for group_id in ordered_ids:
            entry = groups[group_id]
            cells = []
            per_period = entry['per_period']
            for p_idx in range(len(periods)):
                for col in self.column_ids.sorted('sequence'):
                    aggregates = (per_period[p_idx] or {}).get(col.expression_label) or self._hpr_empty_aggregates()
                    value = self._hpr_subformula_value(
                        self._hpr_label_subformula(direct_exps, col.expression_label),
                        aggregates)
                    cells.append(self._hpr_format_cell(value, col, currency))
            unfold_key = f'grp_{line.id}_{group_id}'
            unfolded = bool(options.get('unfolded_lines', {}).get(unfold_key))
            rows.append({
                'id': unfold_key,
                'name': entry['name'],
                'level': line.hierarchy_level + 2,
                'classes': [],
                'foldable': True,
                'unfolded': unfolded,
                'cells': cells,
                'action_id': False,
                'has_more': False,
                'groupby': True,
                'group_record': group_field,
                'group_id': group_id,
            })
            if unfolded:
                rows.extend(self._hpr_get_group_children(
                    line, group_field, group_id, periods, options,
                    exps_by_label, is_aging, currency))
        return rows

    def _hpr_get_group_children(self, line, group_field, group_id, periods, options,
                                exps_by_label, is_aging, currency):
        """Drill-down: individual journal items below a groupby group row."""
        AML_LIMIT = 80
        fetch_exp = exps_by_label.get('total') or next(iter(exps_by_label.values()))
        base_domain = ast.literal_eval(fetch_exp.formula)
        group_domain = self._hpr_apply_date_scope(list(base_domain), fetch_exp.date_scope,
                                                  periods[0], exp=fetch_exp)
        group_domain = self._hpr_apply_base_filters(group_domain, options)
        group_domain += [(group_field, '=', group_id)]

        aml = self.env['account.move.line']
        if is_aging:
            records = aml.search_read(
                group_domain,
                ['balance', 'debit', 'credit', 'amount_residual', 'date', 'date_maturity',
                 'name', 'move_id'],
                limit=AML_LIMIT, order='date, id')
            per_period_records = [(p_idx, records) for p_idx in range(len(periods))]
        else:
            per_period_records = []
            for p_idx, period in enumerate(periods):
                domain = self._hpr_apply_date_scope(list(base_domain), fetch_exp.date_scope,
                                                    period, exp=fetch_exp)
                domain = self._hpr_apply_base_filters(domain, options)
                domain += [(group_field, '=', group_id)]
                recs = aml.search_read(
                    domain,
                    ['balance', 'debit', 'credit', 'amount_residual', 'date', 'date_maturity',
                     'name', 'move_id'],
                    limit=AML_LIMIT, order='date, id')
                per_period_records.append((p_idx, recs))

        rows = []
        for p_idx, recs in per_period_records:
            for vals in recs:
                move = vals.get('move_id') or (False, '')
                move_name = move[1] if isinstance(move, (tuple, list)) else ''
                label = vals.get('name') or ''
                name = f"{vals['date']} {move_name}" + (f" - {label}" if label else '')
                cells = []
                for period in periods:
                    for col in self.column_ids.sorted('sequence'):
                        exp = exps_by_label.get(col.expression_label)
                        if exp is None:
                            value = 0.0
                        elif is_aging and exp.date_scope == 'aging':
                            in_bucket = self._hpr_aml_in_bucket(vals, exp, period['date_to'])
                            value = vals['amount_residual'] or 0.0 if in_bucket else 0.0
                        elif is_aging:
                            value = (vals['amount_residual'] or 0.0) if vals['date'] <= period['date_to'] else 0.0
                        elif p_idx == periods.index(period):
                            sub = (exp.subformula or 'sum').strip()
                            field = {'debit': 'debit', 'credit': 'credit', 'residual': 'amount_residual'}.get(sub, 'balance')
                            value = vals[field] or 0.0
                        else:
                            value = 0.0
                        cells.append(self._hpr_format_cell(value, col, currency))
                rows.append({
                    'id': f"grp_{line.id}_{group_id}_aml_{vals['id']}",
                    'name': name[:120],
                    'level': line.hierarchy_level + 3,
                    'classes': ['hpr-row--aml'],
                    'foldable': False,
                    'unfolded': False,
                    'cells': cells,
                    'action_id': False,
                    'has_more': False,
                    'groupby': False,
                })
        return rows

    @staticmethod
    def _hpr_aml_in_bucket(vals, exp, date_to):
        maturity = vals.get('date_maturity')
        if not maturity:
            return False
        from_days = exp.hpr_aging_from_days
        to_days = exp.hpr_aging_to_days
        if from_days == 0 and to_days == 0:
            return maturity > date_to
        if not maturity <= date_to - timedelta(days=from_days):
            return False
        return to_days >= 100000 or maturity > date_to - timedelta(days=to_days + 1)

    def _hpr_label_subformula(self, expressions, label):
        exp = expressions.filtered(lambda e: e.label == label)
        if exp:
            return exp.subformula or 'sum'
        return 'sum'

    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------

    def _hpr_format_cell(self, value, col, currency):
        blank = value == 0 and (col.blank_if_zero or False)
        figure_type = col.figure_type or 'monetary'
        if blank:
            formatted = ''
        elif figure_type == 'monetary':
            formatted = formatLang(self.env, value, currency_obj=currency)
        elif figure_type == 'percentage':
            formatted = f'{value:.1f}%'
        else:
            formatted = formatLang(self.env, value)
        # Web table shows plain numbers (currency is stated once in the header);
        # the PDF keeps the currency-symbol format.
        plain = '' if blank else (
            formatLang(self.env, value) if figure_type == 'monetary' else formatted)
        return {
            'value': value,
            'formatted': formatted,
            'plain': plain,
            'figure_type': figure_type,
            'classes': 'hpr-cell--negative' if value < 0 else '',
        }

    # -------------------------------------------------------------------------
    # UI metadata
    # -------------------------------------------------------------------------

    def _hpr_get_journals(self, options):
        journals = self.env['account.journal'].search([
            ('company_id', 'in', options.get('hadir_scope_company_ids') or self.env.companies.ids)])
        return [{
            'id': j.id,
            'name': j.name,
            'code': j.code,
            'type': j.type,
            'selected': j.id in (options.get('journals') or []),
        } for j in journals]

    def _hpr_get_reports_list(self):
        Imd = self.env['ir.model.data']
        items = []
        for imd in Imd.sudo().search([
            ('module', '=', 'hadir_account_reports'),
            ('model', '=', 'ir.actions.client'),
        ]):
            action = self.env['ir.actions.client'].browse(imd.res_id).exists()
            if not action or action.tag != 'account_report':
                continue
            try:
                context = ast.literal_eval(action.context or '{}')
            except Exception:
                context = {}
            report_id = context.get('report_id')
            items.append({
                'action_id': action.id,
                'report_id': report_id,
                'name': action.name,
                'is_current': report_id == self.id,
            })
        return sorted(items, key=lambda i: i['name'])
