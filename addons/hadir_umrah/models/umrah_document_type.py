from odoo import fields, models


class UmrahDocumentType(models.Model):
    _name = 'umrah.document.type'
    _description = 'Umrah Document Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        index=True,
        help='Unique technical code, e.g. passport, ktp, kk, photo, marriage_book, vaccine, visa, ticket.')
    sequence = fields.Integer(default=10)
    has_expiry = fields.Boolean(
        string='Has Expiry Date',
        help='Enables tracking of the expiry date on submitted documents.')
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'UNIQUE (code)',
        'The document type code must be unique.')
