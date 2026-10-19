{
    'name': 'HadIr Accounting',
    'summary': 'Enterprise-style accounting features for Odoo 19 Community: '
               'Assets & Depreciation, Deferred Revenue/Expense, Budgets, '
               'Follow-ups and Accounting Dashboard',
    'description': """
HadIr Accounting — Enterprise-style accounting on Community
===========================================================

Adds the accounting features kept for Enterprise on top of the standard
`account` module (distinct model names):

* Assets & Depreciation (`account.asset`): straight-line + degressive
  with prorata temporis, monthly depreciation entries via daily cron,
  disposal wizard.
* Deferred Revenue / Deferred Expense: same engine, separate menus.
* Budgets (`account.budget`): analytic-based planned vs achieved with
  progress bars.
* Follow-ups (`hadir.followup.level`): overdue-based customer levels,
  scheduled reminder emails (Indonesian defaults) and manual sending.
* Accounting Dashboard: OWL client action with bank balances, AR/AP,
  overdue, draft invoices/bills, month revenue/expense and asset values.
""",
    'author': 'HadirApp',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'version': '19.0.1.0.1',
    'application': True,
    'installable': True,
    'depends': [
        'account',
    ],
    'data': [
        'security/hadir_accounting_security.xml',
        'security/ir.model.access.csv',
        'views/account_asset_views.xml',
        'views/account_budget_views.xml',
        'views/hadir_followup_views.xml',
        'views/res_partner_views.xml',
        'data/mail_templates.xml',
        'data/followup_levels.xml',
        'data/ir_cron.xml',
        'data/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hadir_accounting/static/src/accounting_dashboard.scss',
            'hadir_accounting/static/src/accounting_dashboard.js',
            'hadir_accounting/static/src/accounting_dashboard.xml',
        ],
    },
    'demo': [],
}
