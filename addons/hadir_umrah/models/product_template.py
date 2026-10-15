from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_umrah_package = fields.Boolean(
        string='Is Umrah Package',
        index=True,
        help='Mark this product as an Umrah package. It becomes selectable '
             'on Umrah bookings and appears under Travel > Configuration > Umrah Packages.')
    umrah_departure_date = fields.Date(
        string='Departure Date',
        help='Default departure date proposed on sales orders and umrah '
             'bookings created with this package.')
    umrah_return_date = fields.Date(
        string='Return Date',
        help='Default return date proposed on sales orders and umrah '
             'bookings created with this package.')
    document_template_id = fields.Many2one(
        'umrah.document.template',
        string='Document Template',
        help='Document checklist generated for each pilgrim of bookings '
             'created from this package. Falls back to the default template.')
