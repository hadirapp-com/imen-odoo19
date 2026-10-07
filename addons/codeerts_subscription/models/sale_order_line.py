from odoo import api, fields, models

# Normalization factors that convert one plan period's amount into a monthly figure.
# Plan units are week/month/year only (see codeerts.subscription.plan).
INTERVAL_FACTOR = {
    'week': 30.437 / 7.0,   # avg days per month / days per week
    'month': 1.0,
    'year': 1.0 / 12.0,
}


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    recurring_invoice = fields.Boolean(
        string="Recurring",
        compute='_compute_recurring_invoice', store=True, readonly=False, precompute=True,
        help="Whether this line is billed on the subscription's recurring interval.")
    recurring_monthly = fields.Monetary(
        string="Monthly Recurring Revenue",
        compute='_compute_recurring_monthly', store=True,
        currency_field='currency_id',
        help="Normalized monthly recurring revenue (MRR) contributed by this line.")
    parent_line_id = fields.Many2one(
        'sale.order.line', string="Parent Line", ondelete='set null', copy=False,
        help="The subscription line this renewal/upsell line derives from.")

    @api.depends('product_id')
    def _compute_recurring_invoice(self):
        for line in self:
            line.recurring_invoice = line.product_id.recurring_invoice

    @api.depends('price_subtotal', 'recurring_invoice',
                 'order_id.is_subscription', 'order_id.plan_id')
    def _compute_recurring_monthly(self):
        for line in self:
            order = line.order_id
            plan = order.plan_id
            if order.is_subscription and line.recurring_invoice and plan and plan.billing_period_value:
                factor = INTERVAL_FACTOR.get(plan.billing_period_unit, 0.0)
                line.recurring_monthly = line.price_subtotal * factor / plan.billing_period_value
            else:
                line.recurring_monthly = 0.0

    # ------------------------------------------------------------------
    # Recurring invoicing overrides
    # A recurring line is re-billed every period. Standard Odoo would mark it
    # "invoiced" forever after the first invoice; we (a) scope qty_invoiced to the
    # CURRENT period, (b) drive invoice_status by next_invoice_date, and (c) stamp
    # each generated invoice line with the period it covers + full period quantity.
    # ------------------------------------------------------------------
    def _is_recurring_subscription_line(self):
        self.ensure_one()
        return bool(
            self.recurring_invoice and not self.display_type and self.order_id.is_subscription)

    @api.depends('invoice_lines.move_id.state', 'invoice_lines.quantity',
                 'invoice_lines.subscription_period_start',
                 'recurring_invoice', 'order_id.next_invoice_date', 'order_id.plan_id')
    def _compute_qty_invoiced(self):
        # Re-triggered when the period rolls forward so recurring lines reset each period.
        super()._compute_qty_invoiced()

    def _prepare_qty_invoiced(self):
        recurring = self.filtered(lambda l: l._is_recurring_subscription_line())
        others = self - recurring
        result = super(SaleOrderLine, others)._prepare_qty_invoiced()
        for line in recurring:
            period_start = line.order_id._subscription_current_period_start()
            qty = 0.0
            if period_start:
                for invoice_line in line._get_invoice_lines():
                    move = invoice_line.move_id
                    if move.state == 'cancel' and move.payment_state != 'invoicing_legacy':
                        continue
                    if invoice_line.subscription_period_start != period_start:
                        continue
                    invoice_qty = invoice_line.product_uom_id._compute_quantity(
                        invoice_line.quantity, line.product_uom_id, round=False)
                    if move.move_type == 'out_invoice':
                        qty += invoice_qty
                    elif move.move_type == 'out_refund':
                        qty -= invoice_qty
            result[line] = qty
        return result

    @api.depends('state', 'product_uom_qty', 'qty_delivered', 'qty_to_invoice', 'qty_invoiced',
                 'recurring_invoice', 'order_id.is_subscription', 'order_id.subscription_state',
                 'order_id.next_invoice_date', 'order_id.end_date', 'order_id.recurring_monthly')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        today = fields.Date.context_today(self)
        for line in self:
            if not line._is_recurring_subscription_line() or line.state != 'sale':
                continue
            order = line.order_id
            if order.subscription_state in ('churn', 'renewed'):
                line.invoice_status = 'invoiced'
                continue
            due = (
                order.next_invoice_date and order.next_invoice_date <= today
                and (not order.end_date or order.end_date > today))
            line.invoice_status = 'to invoice' if due else 'invoiced'

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        if self._is_recurring_subscription_line():
            order = self.order_id
            period_start = self.env.context.get('subscription_period_start') or order.next_invoice_date
            period_end = self.env.context.get('subscription_period_end')
            if not period_end and period_start and order.plan_id:
                period_end = period_start + order.plan_id.get_period_timedelta()
            if 'quantity' not in optional_values:
                vals['quantity'] = self.product_uom_qty  # bill the full quantity every period
            vals.update({
                'subscription_id': order.id,
                'subscription_period_start': period_start,
                'subscription_period_end': period_end,
            })
        return vals
