from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    subscription_id = fields.Many2one(
        'sale.order', string="Subscription", copy=False,
        help="Subscription this recurring invoice was generated for.")


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    subscription_id = fields.Many2one(
        'sale.order', string="Subscription", copy=False)
    # The billing period this invoice line covers. Community has no deferred_* dates
    # (those are Enterprise), so we carry our own period stamps here. Used to scope a
    # subscription line's qty_invoiced to the current period (see sale.order.line).
    subscription_period_start = fields.Date(string="Period Start", copy=False)
    subscription_period_end = fields.Date(string="Period End", copy=False)
