from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_umrah_package = fields.Boolean(
        string='Is Umrah Package',
        index=True,
        help='Mark this product as an Umrah package. It becomes selectable '
             'on Umrah bookings and appears under Travel > Configuration > Umrah Packages.')
    document_template_id = fields.Many2one(
        'umrah.document.template',
        string='Document Template',
        help='Document checklist generated for each pilgrim of bookings '
             'created from this package. Falls back to the default template.')
