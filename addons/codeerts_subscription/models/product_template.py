from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    recurring_invoice = fields.Boolean(
        string="Recurring",
        help="If set, this product can be sold on a subscription and is billed at the "
             "subscription plan's recurring interval.")
