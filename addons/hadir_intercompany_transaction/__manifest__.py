{
    'name': 'HadIr Intercompany Transaction',
    'summary': 'Intercompany bridge: Purchase RFQ -> Sales Quotation -> Sales Order '
               '-> Customer Invoice -> Vendor Bill with mapping, idempotency, audit and retry',
    'description': """
Intercompany Transaction Bridge
===============================
Connects two companies inside one Odoo 19 Community database:

    Company A (buyer)  RFQ -> bridge -> Company B (seller) Quotation/SO
    Company B invoice (posted) -> bridge -> Company A draft Vendor Bill

Native Odoo documents stay native. The module only provides:
routing configuration, product/tax mapping, the bridge with snapshots,
idempotent synchronization, audit log, error handling and retry.

Odoo 19 Community only: no Enterprise intercompany dependency, no sudo()
for business document creation (integration users per company instead).
""",
    'author': 'HadirApp',
    'website': 'https://hadir.app',
    'license': 'LGPL-3',
    'category': 'Hidden/Tools',
    'version': '19.0.1.0.0',
    'application': True,
    'installable': True,
    'depends': [
        'purchase',
        'sale_management',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/cron.xml',
        'views/intercompany_route_views.xml',
        'views/intercompany_mapping_views.xml',
        'views/intercompany_transaction_views.xml',
        'views/intercompany_move_link_views.xml',
        'views/intercompany_sync_log_views.xml',
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/menus.xml',
    ],
}
