ACTIONS_SPEC = [
    ('action_hpr_balance_sheet', 'hadir_account_reports.hpr_balance_sheet', 'Balance Sheet', 1),
    ('action_hpr_profit_loss', 'hadir_account_reports.hpr_profit_loss', 'Profit and Loss', 2),
    ('action_hpr_trial_balance', 'hadir_account_reports.hpr_trial_balance', 'Trial Balance', 3),
    ('action_hpr_general_ledger', 'hadir_account_reports.hpr_general_ledger', 'General Ledger', 4),
    ('action_hpr_partner_ledger', 'hadir_account_reports.hpr_partner_ledger', 'Partner Ledger', 5),
    ('action_hpr_aged_receivable', 'hadir_account_reports.hpr_aged_receivable', 'Aged Receivable', 6),
    ('action_hpr_aged_payable', 'hadir_account_reports.hpr_aged_payable', 'Aged Payable', 7),
    ('action_hpr_cash_book', 'hadir_account_reports.hpr_cash_book', 'Cash Book', 8),
    ('action_hpr_bank_book', 'hadir_account_reports.hpr_bank_book', 'Bank Book', 9),
    ('action_hpr_tax_report', 'account.generic_tax_report', 'Tax Report', 10),
]

FILTER_FIELDS = [
    'filter_date_range', 'filter_show_draft', 'filter_unfold_all',
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

    # 2. Menus under Accounting > Reporting
    parent = env.ref('account.menu_finance_reports', raise_if_not_found=False)
    if parent:
        section = env.ref('hadir_account_reports.menu_hpr_reports', raise_if_not_found=False)
        if not section:
            section = env['ir.ui.menu'].create({
                'name': 'Financial Reports',
                'parent_id': parent.id,
                'sequence': 2,
                'group_ids': [(6, 0, [env.ref('account.group_account_readonly').id])],
            })
            _ensure_xmlid(env, 'ir.ui.menu', 'menu_hpr_reports', section.id)
        for xmlid, _r, name, sequence in ACTIONS_SPEC:
            action = created_actions.get(xmlid)
            if not action:
                continue
            menu_xmlid = 'menu_' + xmlid.replace('action_', '')
            menu = env.ref(f'hadir_account_reports.{menu_xmlid}', raise_if_not_found=False)
            if menu:
                menu.write({'name': name, 'sequence': sequence, 'action': action})
            else:
                menu = env['ir.ui.menu'].create({
                    'name': name,
                    'parent_id': section.id,
                    'sequence': sequence,
                    'action': action,
                    'group_ids': [(6, 0, [env.ref('account.group_account_readonly').id])],
                })
                _ensure_xmlid(env, 'ir.ui.menu', menu_xmlid, menu.id)

    # 3. Activate the option filters on the generic tax report (its own module
    #    doesn't set them in community); variants inherit from the root report.
    generic = env.ref('account.generic_tax_report', raise_if_not_found=False)
    if generic:
        generic.write({
            'filter_date_range': True,
            'filter_show_draft': True,
            'filter_unfold_all': True,
        })
        if generic.variant_report_ids:
            for field in FILTER_FIELDS:
                generic.variant_report_ids._compute_report_option_filter(field)
