from odoo import fields, models


class SubscriptionCloseReason(models.Model):
    _name = 'codeerts.subscription.close.reason'
    _description = 'Subscription Close Reason'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_protected = fields.Boolean(
        string="System Reason",
        help="System reasons (e.g. End of Contract) are used by automated flows.")
