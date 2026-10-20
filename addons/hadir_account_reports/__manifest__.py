{
    'name': 'HadIr Account Reports (EE-style)',
    'summary': 'Financial reports with Odoo 19 Enterprise look & feel on Community: '
               'Balance Sheet, P&L, Cash Flow, Trial Balance, General Ledger, Partner Ledger, '
               'Aged Receivable/Payable, Cash/Bank Book, Tax Report + PDF/XLSX export',
    'description': """
EE-style Accounting Reports for Odoo 19 Community
=================================================

Builds on the standard `account.report` engine models (already present in
community `account`) and adds what Enterprise keeps for itself:

* computation engine (domain / aggregation / tax_tags / account_codes / external)
* EE-19-style OWL client action (report switcher, date & comparison filters,
  journals, options, hierarchical fold/unfold rows, drill-down)
* standard financial report data (Balance Sheet, Profit & Loss, Trial Balance,
  General Ledger, Partner Ledger, Aged Receivable/Payable, Cash & Bank Book)
* surfacing of the generic tax report (+ country variants such as l10n_id)
* PDF and XLSX export from the report header
""",
    'author': 'HadirApp',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'version': '19.0.4.0.1',
    'application': False,
    'installable': True,
    'post_init_hook': 'post_init_hook',
    'depends': [
        'account',
        'hadir_accounting',
    ],
    'data': [
        'data/account_report_data.xml',
        'data/account_report_data_cf.xml',
        'data/account_report_data_tax.xml',
        'data/account_report_data_stmt.xml',
        'data/account_report_data_depr.xml',
        'data/account_report_data_gl.xml',
        'data/account_report_data_cb.xml',
        'data/menus.xml',
        'views/res_company_views.xml',
        'reports/paperformat.xml',
        'reports/report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hadir_account_reports/static/src/account_report.scss',
            'hadir_account_reports/static/src/account_report.js',
            'hadir_account_reports/static/src/account_report_filters.js',
            'hadir_account_reports/static/src/account_report_table.js',
            'hadir_account_reports/static/src/account_report.xml',
        ],
    },
}
