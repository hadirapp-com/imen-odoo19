from odoo import fields, models


class SubscriptionRevenueProjection(models.TransientModel):
    """Ephemeral rows backing the 'Projected Revenue' smart-button list view.

    One row per upcoming billing period of a subscription: the billing date, the
    amount billed that period, and the running (cumulative) total.
    """
    _name = 'codeerts.subscription.revenue.projection'
    _description = 'Subscription Revenue Projection'
    _order = 'period'

    order_id = fields.Many2one('sale.order', string="Subscription", ondelete='cascade')
    period = fields.Integer(string="Period #")
    date = fields.Date(string="Billing Date")
    amount = fields.Monetary(string="Amount", currency_field='currency_id')
    cumulative = fields.Monetary(string="Cumulative", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string="Currency")
