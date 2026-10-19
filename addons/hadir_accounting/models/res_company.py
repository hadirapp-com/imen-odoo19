from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import formatLang


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def hadir_dashboard_data(self):
        if not self.env.su and not self.env.user.has_group('account.group_account_readonly'):
            raise AccessError(_(
                "Only accounting users can access the accounting dashboard data."))
        company = self.env.company
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        aml = self.env['account.move.line']
        data = {
            'company_id': company.id,
            'company_name': company.name,
            'today': today.strftime('%d %b %Y'),
        }

        # ---- Bank & cash balances -------------------------------------
        journals = self.env['account.journal'].search([
            ('company_id', '=', company.id), ('type', 'in', ('bank', 'cash'))])
        balances = {}
        account_ids = journals.default_account_id.ids
        if account_ids:
            groups = aml._read_group(
                [('account_id', 'in', account_ids), ('parent_state', '=', 'posted')],
                ['account_id'], ['balance:sum'])
            for account, balance in groups:
                balances[account.id] = balance or 0.0
        data['bank_balances'] = [{
            'id': journal.id,
            'name': journal.name,
            'code': journal.code,
            'type': journal.type,
            'balance': balances.get(journal.default_account_id.id, 0.0),
            'balance_formatted': formatLang(self.env, balances.get(journal.default_account_id.id, 0.0),
                                            currency_obj=company.currency_id),
        } for journal in journals]

        # ---- Receivables / payables -----------------------------------
        def open_totals(account_type):
            base = [
                ('account_type', '=', account_type),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('company_id', '=', company.id),
            ]
            groups = aml._read_group(base, [], ['amount_residual:sum'])
            total = groups[0][0] if groups and groups[0][0] else 0.0
            groups = aml._read_group(base + [('date_maturity', '<', today)],
                                     [], ['amount_residual:sum'])
            overdue = groups[0][0] if groups and groups[0][0] else 0.0
            return total, overdue

        ar_total, ar_overdue = open_totals('asset_receivable')
        ap_total, ap_overdue = open_totals('liability_payable')
        data['receivables'] = {'total': ar_total, 'overdue': ar_overdue}
        data['payables'] = {'total': ap_total, 'overdue': ap_overdue}
        for key in ('receivables', 'payables'):
            data[key]['total_formatted'] = formatLang(self.env, data[key]['total'], currency_obj=company.currency_id)
            data[key]['overdue_formatted'] = formatLang(self.env, data[key]['overdue'], currency_obj=company.currency_id)

        # ---- Draft invoices / bills -----------------------------------
        def draft_totals(move_type):
            groups = self.env['account.move']._read_group(
                [('move_type', '=', move_type), ('state', '=', 'draft'),
                 ('company_id', '=', company.id)],
                [], ['amount_total:sum', '__count'])
            amount = groups[0][0] if groups and groups[0][0] else 0.0
            count = groups[0][1] if groups else 0
            return {'count': count, 'amount': amount,
                    'amount_formatted': formatLang(self.env, amount, currency_obj=company.currency_id)}

        data['draft_invoices'] = draft_totals('out_invoice')
        data['draft_bills'] = draft_totals('in_invoice')

        # ---- This month revenue / expenses ----------------------------
        def month_sum(account_types):
            groups = aml._read_group(
                [('date', '>=', month_start), ('date', '<=', today),
                 ('parent_state', '=', 'posted'),
                 ('account_type', 'in', account_types),
                 ('company_id', '=', company.id)],
                [], ['balance:sum'])
            return groups[0][0] if groups and groups[0][0] else 0.0

        revenue = -month_sum(['income', 'income_other'])
        expenses = month_sum(['expense', 'expense_other', 'expense_direct_cost', 'expense_depreciation'])
        data['month'] = {
            'label': month_start.strftime('%B %Y'),
            'revenue': revenue,
            'expenses': expenses,
            'profit': revenue - expenses,
            'revenue_formatted': formatLang(self.env, revenue, currency_obj=company.currency_id),
            'expenses_formatted': formatLang(self.env, expenses, currency_obj=company.currency_id),
            'profit_formatted': formatLang(self.env, revenue - expenses, currency_obj=company.currency_id),
        }

        # ---- Assets ----------------------------------------------------
        asset_groups = self.env['account.asset']._read_group(
            [('state', '=', 'running'), ('company_id', '=', company.id)],
            ['asset_type'], ['book_value:sum', 'original_value:sum', '__count'])
        assets = {'fixed': {}, 'deferred_revenue': {}}
        for asset_type, book, original, count in asset_groups:
            key = 'deferred_revenue' if asset_type == 'sale' else 'fixed'
            assets[key] = {
                'count': count,
                'book_value': book or 0.0,
                'original_value': original or 0.0,
                'book_value_formatted': formatLang(self.env, book or 0.0, currency_obj=company.currency_id),
            }
        data['assets'] = assets

        # ---- Quick links ----------------------------------------------
        links = []
        for xmlid, name in [
            ('account.action_move_out_invoice_type', 'Customer Invoices'),
            ('account.action_move_in_invoice_type', 'Vendor Bills'),
            ('hadir_accounting.action_had_asset', 'Assets & Depreciation'),
            ('hadir_accounting.action_had_deferred', 'Deferred Entries'),
            ('hadir_accounting.action_had_budget', 'Budgets'),
            ('hadir_accounting.action_had_process_followups', 'Follow-ups'),
        ]:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                links.append({'name': name, 'action_id': action.id})
        data['links'] = links
        return data
