{
    'name': 'HadIr Umrah',
    'summary': 'Vertical solution for Umrah travel: packages, bookings, pilgrims, documents, visas, manasik, portal',
    'description': """
Umrah Travel Vertical Solution
==============================

Product Umrah Package -> Sales Order -> Umrah Booking -> Pilgrims
with document checklist, visa processing, manasik sessions,
operational tasks, payment status and automated reminders.

Phase 1 (Core MVP): bookings, pilgrims, documents, payment status.
Phase 2 (Operation): visas, manasik, task automation, reminders, dashboard.
Phase 3 (Portal): jamaah portal "My Umrah" with document upload,
payment view, manasik schedule and flight information.
""",
    'author': 'HadirApp',
    'license': 'LGPL-3',
    'category': 'Services/Travel',
    'version': '19.0.3.0.0',
    'application': True,
    'installable': True,
    'depends': [
        'sale_management',
        'account',
        'project',
        'calendar',
        'portal',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/document_template.xml',
        'data/task_template.xml',
        'data/cron.xml',
        'views/umrah_booking_views.xml',
        'views/umrah_pilgrim_views.xml',
        'views/umrah_document_views.xml',
        'views/umrah_visa_views.xml',
        'views/umrah_manasik_views.xml',
        'views/umrah_task_views.xml',
        'views/umrah_flight_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/umrah_portal_templates.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'images': [
        'static/description/icon.png',
    ],
}
