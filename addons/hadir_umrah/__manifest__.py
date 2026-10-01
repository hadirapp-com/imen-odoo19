{
    'name': 'HadIr Umrah',
    'summary': 'Vertical solution for Umrah travel: packages, bookings, pilgrims, document checklist',
    'description': """
Umrah Travel Vertical Solution
==============================

Product Umrah Package -> Sales Order -> Umrah Booking -> Pilgrims
with document checklist, payment status and operational reminders.

Phase 1 (Core MVP). Phase 2 adds Visa, Manasik and operational tasks.
""",
    'author': 'HadirApp',
    'license': 'LGPL-3',
    'category': 'Services/Travel',
    'version': '19.0.1.0.0',
    'application': True,
    'installable': True,
    'depends': [
        'sale_management',
        'account',
        'project',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/document_template.xml',
        'data/cron.xml',
        'views/umrah_booking_views.xml',
        'views/umrah_pilgrim_views.xml',
        'views/umrah_document_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'images': [
        'static/description/icon.png',
    ],
}
