ACTIONS_SPEC = [
    ('action_hpr_balance_sheet', 'hadir_account_reports.hpr_balance_sheet', 'Balance Sheet', 1),
    ('action_hpr_profit_loss', 'hadir_account_reports.hpr_profit_loss', 'Profit and Loss', 2),
    ('action_hpr_cash_flow', 'hadir_account_reports.hpr_cash_flow', 'Cash Flow Statement', 3),
    ('action_hpr_trial_balance', 'hadir_account_reports.hpr_trial_balance', 'Trial Balance', 4),
    ('action_hpr_general_ledger', 'hadir_account_reports.hpr_general_ledger', 'General Ledger', 5),
    ('action_hpr_partner_ledger', 'hadir_account_reports.hpr_partner_ledger', 'Partner Ledger', 6),
    ('action_hpr_aged_receivable', 'hadir_account_reports.hpr_aged_receivable', 'Aged Receivable', 7),
    ('action_hpr_aged_payable', 'hadir_account_reports.hpr_aged_payable', 'Aged Payable', 8),
    ('action_hpr_cash_book', 'hadir_account_reports.hpr_cash_book', 'Cash Book', 9),
    ('action_hpr_bank_book', 'hadir_account_reports.hpr_bank_book', 'Bank Book', 10),
    ('action_hpr_tax_report', 'hadir_account_reports.hpr_tax_report', 'Tax Report', 11),
    ('action_hpr_customer_statement', 'hadir_account_reports.hpr_customer_statement',
     'Customer Statement', 12),
    ('action_hpr_depreciation_schedule', 'hadir_account_reports.hpr_depreciation_schedule',
     'Depreciation Schedule', 13),
]


def post_init_hook(env):
    """Create the `account_report` client actions + menus and activate the
    EE-style option filters on every report bound to an action.

    The `account.report` option-filter fields are computed by searching for an
    ir.actions.client with tag 'account_report' whose context embeds the report
    id, so the actions must exist before the flags can be recomputed.
    """
    setup_actions_and_menus(env)


def _ensure_xmlid(env, model, xmlid, res_id, noupdate=True):
    Imd = env['ir.model.data']
    existing = Imd.sudo().search([('module', '=', 'hadir_account_reports'), ('name', '=', xmlid)])
    if existing:
        return
    Imd.sudo().create({
        'module': 'hadir_account_reports',
        'name': xmlid,
        'model': model,
        'res_id': res_id,
        'noupdate': noupdate,
    })


def setup_actions_and_menus(env):
    # 1. Client actions (tag must be exactly 'account_report', context embeds report id)
    created_actions = {}
    for xmlid, report_xmlid, name, _sequence in ACTIONS_SPEC:
        report = env.ref(report_xmlid, raise_if_not_found=False)
        if not report:
            continue
        action = env.ref(f'hadir_account_reports.{xmlid}', raise_if_not_found=False)
        action_vals = {
            'name': name,
            'tag': 'account_report',
            'context': str({'report_id': report.id}),
            'params': str({'report_id': report.id}),
        }
        if action:
            action.write(action_vals)
        else:
            action = env['ir.actions.client'].create(action_vals)
            _ensure_xmlid(env, 'ir.actions.client', xmlid, action.id)
        created_actions[xmlid] = action

    # 2. Single menu under Accounting > Reporting. One entry opens the engine
    #    (Balance Sheet); the report picker dropdown in the toolbar covers the
    #    remaining reports, so per-report menus are redundant.
    parent = env.ref('account.menu_finance_reports', raise_if_not_found=False)
    if parent:
        action = created_actions.get('action_hpr_balance_sheet')
        section = env.ref('hadir_account_reports.menu_hpr_reports', raise_if_not_found=False)
        if not section:
            section = env['ir.ui.menu'].create({
                'name': 'Financial Reports',
                'parent_id': parent.id,
                'sequence': 2,
                'action': action,
                'group_ids': [(6, 0, [env.ref('account.group_account_readonly').id])],
            })
            _ensure_xmlid(env, 'ir.ui.menu', 'menu_hpr_reports', section.id)
        elif section.action != action:
            section.write({'action': action})
        Imd = env['ir.model.data']
        stale = Imd.sudo().search([
            ('module', '=', 'hadir_account_reports'),
            ('model', '=', 'ir.ui.menu'),
            ('name', 'in', ['menu_' + xmlid.replace('action_', '')
                            for xmlid, _r, _n, _s in ACTIONS_SPEC]),
        ])
        for imd in stale:
            menu = env['ir.ui.menu'].browse(imd.res_id).exists()
            imd.unlink()
            if menu:
                menu.unlink()

    # 3. Partner picker visibility on partner-centric reports (re-asserted
    #    here because core recomputes option flags from action existence).
    for report_xmlid in ('hpr_partner_ledger', 'hpr_aged_receivable',
                         'hpr_aged_payable', 'hpr_customer_statement'):
        report = env.ref(f'hadir_account_reports.{report_xmlid}',
                         raise_if_not_found=False)
        if report and not report.filter_partner:
            report.write({'filter_partner': True})
