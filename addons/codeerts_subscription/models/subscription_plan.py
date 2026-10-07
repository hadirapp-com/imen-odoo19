from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionPlan(models.Model):
    _name = 'codeerts.subscription.plan'
    _description = 'Subscription Plan'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    # --- Recurrence ------------------------------------------------------
    billing_period_value = fields.Integer(
        string="Billing Every", default=1, required=True,
        help="Number of billing period units between two invoices.")
    billing_period_unit = fields.Selection(
        selection=[
            ('week', 'Weeks'),
            ('month', 'Months'),
            ('year', 'Years'),
        ],
        string="Billing Period", default='month', required=True)
    billing_first_day = fields.Boolean(
        string="Align to First Day",
        help="Align every invoice to the first day of the billing period (months/years only).")
    auto_close_limit = fields.Integer(
        string="Automatic Closing (days)", default=15,
        help="Number of days after the invoice date before an unpaid subscription is "
             "automatically closed.")

    # --- Customer self-service (portal) ---------------------------------
    user_closable = fields.Boolean(
        string="Closable by Customer",
        help="Allow the customer to close the subscription from the portal.")
    user_closable_options = fields.Selection(
        selection=[
            ('at_date', 'Immediately'),
            ('end_of_period', 'At End of Billing Period'),
        ],
        string="Customer Closing", default='at_date', required=True)
    user_extend = fields.Boolean(
        string="Renewable by Customer",
        help="Allow the customer to request a renewal from the portal.")
    user_quantity = fields.Boolean(
        string="Upsell by Customer",
        help="Allow the customer to request a quantity change from the portal.")
    pausable = fields.Boolean(
        string="Pausable by Customer",
        help="Allow the customer to temporarily pause the subscription from the portal.")

    invoice_mail_template_id = fields.Many2one(
        'mail.template', string="Invoice Email Template",
        domain="[('model', '=', 'account.move')]",
        help="Email template used to send the recurring invoice to the customer.")

    # v19 SQL constraint style (models.Constraint). v18 down-port -> _sql_constraints.
    _billing_period_positive = models.Constraint(
        'CHECK(billing_period_value > 0)',
        'The billing period must be strictly positive.',
    )
    _auto_close_limit_positive = models.Constraint(
        'CHECK(auto_close_limit >= 0)',
        'The automatic closing delay cannot be negative.',
    )

    def get_period_timedelta(self):
        """Return a ``relativedelta`` representing one billing period of this plan.

        ``relativedelta`` (not ``timedelta``) so month/year arithmetic lands on the
        correct calendar day.
        """
        self.ensure_one()
        unit, value = self.billing_period_unit, self.billing_period_value
        if unit == 'week':
            return relativedelta(weeks=value)
        if unit == 'month':
            return relativedelta(months=value)
        if unit == 'year':
            return relativedelta(years=value)
        return relativedelta()
