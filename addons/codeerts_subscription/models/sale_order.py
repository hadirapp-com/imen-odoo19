import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Safety cap on how many periods we project (e.g. weekly plans, far-off end dates).
PROJECTION_PERIOD_CAP = 120
# Safety cap on catch-up billing in a single cron pass (avoids runaway loops).
CATCHUP_PERIOD_CAP = 36


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    plan_id = fields.Many2one(
        'codeerts.subscription.plan', string="Recurring Plan",
        ondelete='restrict', copy=True,
        help="Choose a recurring plan to turn this order into a subscription.")
    is_subscription = fields.Boolean(
        string="Is a Subscription",
        compute='_compute_is_subscription', store=True, index=True)
    subscription_state = fields.Selection(
        selection=[
            ('draft', 'Quotation'),
            ('progress', 'In Progress'),
            ('paused', 'Paused'),
            ('renewed', 'Renewed'),
            ('churn', 'Closed'),
            ('upsell', 'Upsell'),
            ('renewal', 'Renewal Quotation'),
        ],
        string="Subscription Status",
        compute='_compute_subscription_state', store=True, readonly=False,
        index=True, copy=False, tracking=True)

    start_date = fields.Date(
        string="Start Date", copy=False,
        help="Date on which the subscription starts and recurring invoicing begins.")
    next_invoice_date = fields.Date(
        string="Next Invoice Date", copy=False, readonly=True,
        help="Date on which the next recurring invoice will be generated.")
    end_date = fields.Date(
        string="End Date", copy=False,
        help="If set, the subscription is automatically closed on this date.")
    close_reason_id = fields.Many2one(
        'codeerts.subscription.close.reason', string="Close Reason", copy=False, tracking=True)

    subscription_id = fields.Many2one(
        'sale.order', string="Parent Subscription", copy=False, ondelete='restrict',
        help="The subscription this renewal or upsell order derives from.")
    origin_order_id = fields.Many2one(
        'sale.order', string="Origin Subscription",
        compute='_compute_origin_order_id', store=True, recursive=True,
        help="The first subscription in the renewal chain.")
    subscription_child_ids = fields.One2many(
        'sale.order', 'subscription_id', string="Renewals & Upsells")
    subscription_child_count = fields.Integer(compute='_compute_subscription_child_count')

    recurring_monthly = fields.Monetary(
        string="Monthly Recurring Revenue",
        compute='_compute_recurring_monthly', store=True, tracking=True,
        currency_field='currency_id',
        help="Normalized monthly recurring revenue (MRR) of this subscription.")
    recurring_total = fields.Monetary(
        string="Recurring Total",
        compute='_compute_recurring_totals', store=True,
        currency_field='currency_id',
        help="Total untaxed recurring amount billed each plan period.")
    expected_revenue = fields.Monetary(
        string="Projected Revenue",
        compute='_compute_expected_revenue',
        currency_field='currency_id',
        help="Estimated revenue over the subscription term (start date to end date). "
             "When no end date is set, this is projected over the next 12 months.")
    expected_revenue_periods = fields.Integer(
        string="Projected Periods",
        compute='_compute_expected_revenue')

    payment_token_id = fields.Many2one(
        'payment.token', string="Payment Token", copy=False,
        help="Saved payment method automatically charged for each recurring invoice.")
    payment_exception = fields.Boolean(
        string="Payment Exception", copy=False,
        help="An automatic payment failed; recurring invoicing is paused until resolved.")
    recurring_invoice_due = fields.Boolean(
        string="Recurring Invoice Due", compute='_compute_recurring_invoice_due',
        help="True when a recurring invoice is currently due (the next invoice date has "
             "arrived). Drives the highlighted 'Generate Invoice' button.")

    @api.depends('plan_id', 'subscription_state')
    def _compute_is_subscription(self):
        for order in self:
            order.is_subscription = bool(order.plan_id) and order.subscription_state != 'upsell'

    @api.depends('subscription_id', 'subscription_id.origin_order_id')
    def _compute_origin_order_id(self):
        for order in self:
            order.origin_order_id = (
                order.subscription_id.origin_order_id or order.subscription_id or order)

    def _compute_subscription_child_count(self):
        for order in self:
            order.subscription_child_count = len(order.subscription_child_ids)

    @api.depends('plan_id')
    def _compute_subscription_state(self):
        # Set the initial state once; actions (confirm/close/renew/upsell) write it afterwards.
        for order in self:
            if order.subscription_state:
                continue
            order.subscription_state = 'draft' if order.plan_id else False

    @api.depends('order_line.recurring_monthly')
    def _compute_recurring_monthly(self):
        for order in self:
            order.recurring_monthly = sum(order.order_line.mapped('recurring_monthly'))

    @api.depends('order_line.price_subtotal', 'order_line.recurring_invoice')
    def _compute_recurring_totals(self):
        for order in self:
            order.recurring_total = sum(
                order.order_line.filtered('recurring_invoice').mapped('price_subtotal'))

    @api.depends('is_subscription', 'subscription_state', 'next_invoice_date', 'end_date')
    def _compute_recurring_invoice_due(self):
        today = fields.Date.context_today(self)
        for order in self:
            order.recurring_invoice_due = bool(
                order.is_subscription and order.subscription_state == 'progress'
                and order.next_invoice_date and order.next_invoice_date <= today
                and (not order.end_date or order.end_date > today))

    @api.depends('recurring_total', 'plan_id', 'start_date', 'end_date', 'is_subscription')
    def _compute_expected_revenue(self):
        for order in self:
            schedule = order._get_revenue_projection()
            order.expected_revenue_periods = len(schedule)
            order.expected_revenue = schedule[-1]['cumulative'] if schedule else 0.0

    def _get_revenue_projection(self):
        """Return the projected billing schedule as a list of dicts.

        One entry per billing period from the start date to the end date. When no
        end date is set, the horizon is one year forward (subscription keeps billing).
        Each entry: {period, date, amount, cumulative}.
        """
        self.ensure_one()
        if not self.is_subscription or not self.plan_id:
            return []
        start = self.start_date or fields.Date.context_today(self)
        if self.end_date and self.end_date > start:
            horizon_end = self.end_date
        else:
            horizon_end = start + relativedelta(years=1)
        period_delta = self.plan_id.get_period_timedelta()
        schedule, cumulative, billing_date, period = [], 0.0, start, 1
        while billing_date < horizon_end and period <= PROJECTION_PERIOD_CAP:
            cumulative += self.recurring_total
            schedule.append({
                'period': period,
                'date': billing_date,
                'amount': self.recurring_total,
                'cumulative': cumulative,
            })
            billing_date += period_delta
            period += 1
        return schedule

    def action_revenue_projection(self):
        """Smart-button click: build the projection schedule and open it as a list."""
        self.ensure_one()
        Projection = self.env['codeerts.subscription.revenue.projection']
        rows = [
            dict(entry, order_id=self.id, currency_id=self.currency_id.id)
            for entry in self._get_revenue_projection()
        ]
        records = Projection.create(rows) if rows else Projection.browse()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Revenue Projection: %s", self.name),
            'res_model': 'codeerts.subscription.revenue.projection',
            'view_mode': 'list',
            'views': [(self.env.ref('codeerts_subscription.view_revenue_projection_list').id, 'list')],
            'domain': [('id', 'in', records.ids)],
            'target': 'new',
            'context': {'create': False, 'edit': False, 'delete': False},
        }

    # ==================================================================
    # Recurring invoicing engine
    # ==================================================================
    def _subscription_current_period_start(self):
        """Start date of the subscription's current (most recently billed) period.

        Equals next_invoice_date minus one plan period. Used to scope a recurring
        line's qty_invoiced to the current period only (see sale.order.line).
        """
        self.ensure_one()
        if not self.plan_id or not self.next_invoice_date:
            return False
        return self.next_invoice_date - self.plan_id.get_period_timedelta()

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.is_subscription:
            vals['subscription_id'] = self.id
        return vals

    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final=final)
        # Recurring subscription lines are billed ONLY by the subscription engine
        # (recurring_automatic context). Keep them out of the standard invoice flow so the
        # standard "Create Invoice" wizard can never double-bill them or produce an invoice
        # that does not advance next_invoice_date.
        lines -= lines.filtered(lambda l: l._is_recurring_subscription_line())
        if not self.env.context.get('recurring_automatic'):
            return lines
        today = fields.Date.context_today(self)
        for order in self:
            if not order.is_subscription or order.subscription_state != 'progress':
                continue
            if not order.next_invoice_date or order.next_invoice_date > today:
                continue
            if order.end_date and order.end_date <= today:
                continue
            lines |= order.order_line.filtered(
                lambda l: l._is_recurring_subscription_line() and l.product_uom_qty)
        return lines

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            if order.subscription_state == 'renewal':
                order._confirm_renewal()
            elif order.subscription_state == 'upsell':
                order._confirm_upsell()
            elif order.is_subscription and order.subscription_state not in (
                    'progress', 'paused', 'renewed', 'churn'):
                order._subscription_start()
        return res

    # ==================================================================
    # Renew & Upsell
    # ==================================================================
    def _get_upsell_ratio(self):
        """Fraction of the current billing period still remaining (0..1)."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        end = self.next_invoice_date
        if not self.plan_id or not end or today >= end:
            return 0.0
        remaining = (end - today).days
        full = ((today + self.plan_id.get_period_timedelta()) - today).days
        return remaining / full if full else 0.0

    def _prepare_renewal_order_values(self):
        self.ensure_one()
        lines = [(0, 0, {
            'product_id': line.product_id.id,
            'name': line.name,
            'product_uom_qty': line.product_uom_qty,
            'price_unit': line.price_unit,
            'discount': line.discount,
            'parent_line_id': line.id,
        }) for line in self.order_line.filtered(lambda l: l.recurring_invoice and not l.display_type)]
        return {
            'partner_id': self.partner_id.id,
            'partner_invoice_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'pricelist_id': self.pricelist_id.id,
            'payment_term_id': self.payment_term_id.id,
            'plan_id': self.plan_id.id,
            'subscription_id': self.id,
            'subscription_state': 'renewal',
            'start_date': self.next_invoice_date,
            'order_line': lines,
        }

    def action_subscription_renew(self):
        self.ensure_one()
        renewal = self.env['sale.order'].create(self._prepare_renewal_order_values())
        return {
            'type': 'ir.actions.act_window', 'name': _("Renewal Quotation"),
            'res_model': 'sale.order', 'res_id': renewal.id,
            'view_mode': 'form', 'target': 'current',
        }

    def _confirm_renewal(self):
        self.ensure_one()
        parent = self.subscription_id
        today = fields.Date.context_today(self)
        self.write({'subscription_state': 'progress'})
        if not self.next_invoice_date:
            self.next_invoice_date = self.start_date or today
        if parent:
            parent_mrr = parent.recurring_monthly
            parent.write({'subscription_state': 'renewed', 'end_date': self.start_date or today})
            parent._log_subscription_event('4_transfer', 0.0, -parent_mrr)
        self._log_subscription_event('4_transfer', self.recurring_monthly, self.recurring_monthly)

    def _prepare_upsell_order_values(self):
        self.ensure_one()
        disc = round((1 - self._get_upsell_ratio()) * 100, 2)
        lines = [(0, 0, {
            'product_id': line.product_id.id,
            'name': line.name,
            'product_uom_qty': 0.0,  # customer enters the additional quantity
            'price_unit': line.price_unit,
            'discount': disc,
            'parent_line_id': line.id,
        }) for line in self.order_line.filtered(lambda l: l.recurring_invoice and not l.display_type)]
        return {
            'partner_id': self.partner_id.id,
            'partner_invoice_id': self.partner_invoice_id.id,
            'pricelist_id': self.pricelist_id.id,
            'payment_term_id': self.payment_term_id.id,
            'plan_id': self.plan_id.id,
            'subscription_id': self.id,
            'subscription_state': 'upsell',
            'start_date': fields.Date.context_today(self),
            'order_line': lines,
        }

    def action_subscription_upsell(self):
        self.ensure_one()
        upsell = self.env['sale.order'].create(self._prepare_upsell_order_values())
        return {
            'type': 'ir.actions.act_window', 'name': _("Upsell Quotation"),
            'res_model': 'sale.order', 'res_id': upsell.id,
            'view_mode': 'form', 'target': 'current',
        }

    def _confirm_upsell(self):
        self.ensure_one()
        parent = self.subscription_id
        if not parent:
            return
        mrr_before = parent.recurring_monthly
        # Prorate the upsell lines to the remaining period, then invoice them (standard flow).
        disc = round((1 - parent._get_upsell_ratio()) * 100, 2)
        recurring = self.order_line.filtered(
            lambda l: l.recurring_invoice and not l.display_type and l.product_uom_qty)
        recurring.write({'discount': disc})
        moves = self.with_context(raise_if_nothing_to_invoice=False)._create_invoices()
        if moves:
            moves.action_post()
        # Merge the added quantities into the parent subscription (full price going forward).
        for line in recurring:
            if line.parent_line_id:
                line.parent_line_id.product_uom_qty += line.product_uom_qty
            else:
                parent.write({'order_line': [(0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'product_uom_qty': line.product_uom_qty,
                    'price_unit': line.price_unit,
                })]})
        delta = parent.recurring_monthly - mrr_before
        parent._log_subscription_event('1_expansion', parent.recurring_monthly, delta)

    def action_view_subscription_children(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Renewals & Upsells"),
            'res_model': 'sale.order',
            'domain': [('id', 'in', self.subscription_child_ids.ids)],
            'view_mode': 'list,form',
        }

    def _subscription_start(self):
        """Activate a confirmed subscription: set dates + state, log MRR creation."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        vals = {'subscription_state': 'progress'}
        if not self.start_date:
            vals['start_date'] = today
        if not self.next_invoice_date:
            vals['next_invoice_date'] = self.start_date or today
        self.write(vals)
        self._log_subscription_event('0_creation', self.recurring_monthly, self.recurring_monthly)

    def _log_subscription_event(self, event_type, mrr_after, amount_signed):
        """Write an MRR-change log row (sudo: engine may run as a non-privileged user)."""
        self.ensure_one()
        self.env['codeerts.subscription.log'].sudo().create({
            'order_id': self.id,
            'event_type': event_type,
            'recurring_monthly': mrr_after,
            'amount_signed': amount_signed,
            'currency_id': self.currency_id.id,
            'plan_id': self.plan_id.id,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'team_id': self.team_id.id,
            'company_id': self.company_id.id,
        })

    def _subscription_generate_invoice(self):
        """Generate and post one recurring invoice for the current period, then advance
        next_invoice_date by one plan period. Returns the created move(s)."""
        self.ensure_one()
        if self.subscription_state != 'progress' or not self.plan_id or not self.next_invoice_date:
            return self.env['account.move']
        period_start = self.next_invoice_date
        period_end = period_start + self.plan_id.get_period_timedelta()
        order = self.with_context(
            subscription_period_start=period_start,
            subscription_period_end=period_end,
            recurring_automatic=True,
            raise_if_nothing_to_invoice=False,
        )
        moves = order._create_invoices(final=True)
        if not moves:
            return moves
        moves.action_post()
        self.next_invoice_date = period_end
        if self.payment_token_id:
            for move in moves:
                self._subscription_charge_invoice(move)
        return moves

    def _subscription_charge_invoice(self, invoice):
        """Auto-charge the saved token for a posted recurring invoice, then reconcile.

        On success: payment created + invoice reconciled, payment_exception cleared.
        On failure: payment_exception set (recurring billing pauses until resolved).
        """
        self.ensure_one()
        token = self.payment_token_id
        if not token or invoice.amount_total <= 0:
            return False
        tx = self.env['payment.transaction'].create({
            'provider_id': token.provider_id.id,
            'payment_method_id': token.payment_method_id.id,
            'token_id': token.id,
            'amount': invoice.amount_total,
            'currency_id': invoice.currency_id.id,
            'partner_id': self.partner_id.id,
            'operation': 'offline',
            'invoice_ids': [(6, 0, invoice.ids)],
        })
        try:
            # v19: _charge_with_token wraps _send_payment_request + catches ValidationError.
            # (v18 down-port: call tx._send_payment_request() inside try/except instead.)
            tx._charge_with_token()
        except Exception:
            _logger.exception("Subscription auto-charge errored for %s", self.display_name)
        if tx.state == 'done':
            tx._post_process()  # posts invoice (if draft) + creates payment + reconciles
            self.payment_exception = False
            return True
        self.payment_exception = True
        self.message_post(
            body=_("Automatic payment failed for invoice %s.", invoice.name or ''))
        return False

    def action_subscription_retry_payment(self):
        """Manual retry of the oldest unpaid recurring invoice."""
        self.ensure_one()
        invoice = self.env['account.move'].search([
            ('subscription_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ], order='invoice_date asc, id asc', limit=1)
        if invoice and self.payment_token_id:
            self._subscription_charge_invoice(invoice)
        return True

    def action_subscription_generate_invoice(self):
        """Manual 'Generate Invoice' button on the subscription form."""
        moves = self.env['account.move']
        for order in self:
            moves |= order._subscription_generate_invoice()
        if len(moves) == 1:
            return {
                'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'res_id': moves.id, 'view_mode': 'form', 'target': 'current',
            }
        if moves:
            return {
                'type': 'ir.actions.act_window', 'name': _("Invoices"),
                'res_model': 'account.move', 'domain': [('id', 'in', moves.ids)],
                'view_mode': 'list,form',
            }
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("Nothing to invoice"),
                'message': _("No recurring invoice is currently due for this subscription."),
                'type': 'warning', 'sticky': False,
            },
        }

    # ==================================================================
    # Lifecycle: pause / resume / close (churn) / reopen / expiration
    # ==================================================================
    def action_subscription_pause(self):
        self.filtered(lambda o: o.subscription_state == 'progress').write(
            {'subscription_state': 'paused'})
        return True

    def action_subscription_resume(self):
        self.filtered(lambda o: o.subscription_state == 'paused').write(
            {'subscription_state': 'progress'})
        return True

    def action_subscription_close(self):
        """Open the close wizard (pick a reason + immediate/end-of-period)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Close Subscription"),
            'res_model': 'codeerts.subscription.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _subscription_close(self, close_reason=None, end_date=None):
        """Churn the subscription now: state -> churn, log the MRR removal."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        mrr = self.recurring_monthly
        self.write({
            'subscription_state': 'churn',
            'close_reason_id': close_reason.id if close_reason else self.close_reason_id.id,
            'end_date': end_date or self.end_date or today,
        })
        self._log_subscription_event('3_churn', 0.0, -mrr)

    def action_subscription_reopen(self):
        for order in self.filtered(lambda o: o.subscription_state == 'churn'):
            order.write({
                'subscription_state': 'progress',
                'end_date': False,
                'close_reason_id': False,
            })
            order._log_subscription_event('1_expansion', order.recurring_monthly, order.recurring_monthly)
        return True

    def _cron_subscription_expiration(self):
        """Weekly cron: churn subscriptions whose end date has passed."""
        today = fields.Date.context_today(self)
        reason = self.env.ref(
            'codeerts_subscription.close_reason_end_of_contract', raise_if_not_found=False)
        expiring = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ('progress', 'paused')),
            ('end_date', '!=', False),
            ('end_date', '<=', today),
        ])
        for sub in expiring:
            try:
                with self.env.cr.savepoint():
                    sub._subscription_close(close_reason=reason or sub.close_reason_id)
            except Exception:
                _logger.exception(
                    "Subscription expiration failed for %s", sub.display_name)

        # Dunning: close subscriptions whose auto-payment has failed and whose oldest unpaid
        # recurring invoice is overdue by more than the plan's auto-close limit.
        unpaid_reason = self.env.ref(
            'codeerts_subscription.close_reason_payment_failed', raise_if_not_found=False)
        dunning = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'progress'),
            ('payment_exception', '=', True),
        ])
        for sub in dunning:
            invoice = self.env['account.move'].search([
                ('subscription_id', '=', sub.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
            ], order='invoice_date asc, id asc', limit=1)
            limit_days = sub.plan_id.auto_close_limit if sub.plan_id else 15
            if invoice and invoice.invoice_date and (today - invoice.invoice_date).days >= limit_days:
                try:
                    with self.env.cr.savepoint():
                        sub._subscription_close(close_reason=unpaid_reason or sub.close_reason_id)
                except Exception:
                    _logger.exception("Dunning close failed for %s", sub.display_name)
        return True

    def _cron_recurring_invoices(self):
        """Daily cron: bill every subscription whose next invoice is due (with bounded catch-up)."""
        today = fields.Date.context_today(self)
        subs = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'progress'),
            ('state', '=', 'sale'),
            ('payment_exception', '=', False),
            ('next_invoice_date', '!=', False),
            ('next_invoice_date', '<=', today),
        ])
        for sub in subs:
            try:
                with self.env.cr.savepoint():
                    guard = 0
                    while (sub.subscription_state == 'progress' and sub.next_invoice_date
                           and sub.next_invoice_date <= today
                           and (not sub.end_date or sub.end_date > today)
                           and guard < CATCHUP_PERIOD_CAP):
                        moves = sub._subscription_generate_invoice()
                        if not moves:
                            break
                        guard += 1
            except Exception:
                _logger.exception(
                    "Recurring invoicing failed for subscription %s", sub.display_name)
        return True

    # ==================================================================
    # Dashboard data (public entry for the OWL dashboard)
    # ==================================================================
    @api.model
    def get_subscription_dashboard_data(self, filters=None):
        filters = filters or {}
        today = fields.Date.context_today(self)
        plan_id = int(filters['plan_id']) if filters.get('plan_id') else False
        team_id = int(filters['team_id']) if filters.get('team_id') else False
        user_id = int(filters['user_id']) if filters.get('user_id') else False
        date_from = filters.get('date_from') or (
            today.replace(day=1) - relativedelta(months=11)).isoformat()
        date_to = filters.get('date_to') or today.isoformat()

        extra = []
        if plan_id:
            extra.append(('plan_id', '=', plan_id))
        if team_id:
            extra.append(('team_id', '=', team_id))
        if user_id:
            extra.append(('user_id', '=', user_id))

        subs = self.search_read(
            [('is_subscription', '=', True), ('subscription_state', '!=', False)] + extra,
            ['subscription_state', 'recurring_monthly', 'plan_id', 'partner_id',
             'start_date', 'expected_revenue', 'payment_exception', 'next_invoice_date'])
        active = [s for s in subs if s['subscription_state'] == 'progress']
        paused = [s for s in subs if s['subscription_state'] == 'paused']
        active_count = len(active)
        mrr = sum(s['recurring_monthly'] for s in active)
        soon = today + relativedelta(days=30)
        payment_issues = sum(1 for s in subs if s.get('payment_exception'))
        renewing_soon = sum(1 for s in active
                            if s['next_invoice_date'] and today <= s['next_invoice_date'] <= soon)

        def _age_months(s):
            if not s['start_date']:
                return 0.0
            return max(0, (today - fields.Date.to_date(s['start_date'])).days) / 30.437
        avg_len = round(sum(_age_months(s) for s in active) / active_count, 1) if active_count else 0

        palette = {'draft': '#94a3b8', 'progress': '#15a89b', 'paused': '#f59e0b',
                   'renewed': '#6366f1', 'churn': '#ef4444'}
        labels = dict(self._fields['subscription_state']._description_selection(self.env))
        swimlane = []
        for st in ['draft', 'progress', 'paused', 'renewed', 'churn']:
            grp = [s for s in subs if s['subscription_state'] == st]
            swimlane.append({
                'state': st, 'label': labels.get(st, st), 'color': palette[st],
                'count': len(grp), 'mrr': round(sum(g['recurring_monthly'] for g in grp), 2)})

        Log = self.env['codeerts.subscription.log']
        logs = Log.search_read(
            [('event_date', '>=', date_from), ('event_date', '<=', date_to)] + extra,
            ['event_type', 'amount_signed'])

        def _sum(t):
            return round(sum(l['amount_signed'] for l in logs if l['event_type'] == t), 2)
        new_count = len([l for l in logs if l['event_type'] == '0_creation'])
        churn_count = len([l for l in logs if l['event_type'] == '3_churn'])

        all_logs = Log.search_read(extra, ['amount_signed', 'event_date', 'event_type'])
        months = [today.replace(day=1) - relativedelta(months=i) for i in range(11, -1, -1)]
        trend_labels, trend_data = [], []
        mv_new, mv_churn, subs_count = [], [], []
        for mth in months:
            month_end = mth + relativedelta(months=1) - relativedelta(days=1)
            cum = sum(l['amount_signed'] for l in all_logs if l['event_date'] and l['event_date'] <= month_end)
            trend_labels.append(mth.strftime('%b %y'))
            trend_data.append(round(cum, 2))
            in_month = [l for l in all_logs if l['event_date'] and mth <= l['event_date'] <= month_end]
            mv_new.append(sum(1 for l in in_month if l['event_type'] == '0_creation'))
            mv_churn.append(sum(1 for l in in_month if l['event_type'] == '3_churn'))
            upto = [l for l in all_logs if l['event_date'] and l['event_date'] <= month_end]
            subs_count.append(sum(1 for l in upto if l['event_type'] == '0_creation')
                              - sum(1 for l in upto if l['event_type'] == '3_churn'))

        by_plan, plan_names, by_cust, cust_names = {}, {}, {}, {}
        for s in active:
            pid = s['plan_id'][0] if s['plan_id'] else False
            by_plan[pid] = by_plan.get(pid, 0) + s['recurring_monthly']
            plan_names[pid] = s['plan_id'][1] if s['plan_id'] else 'None'
            cid = s['partner_id'][0] if s['partner_id'] else False
            by_cust[cid] = by_cust.get(cid, 0) + s['recurring_monthly']
            cust_names[cid] = s['partner_id'][1] if s['partner_id'] else '-'
        plan_items = sorted(by_plan.items(), key=lambda x: -x[1])
        top = sorted(by_cust.items(), key=lambda x: -x[1])[:6]

        currency = self.env.company.currency_id
        return {
            'currency': {'symbol': currency.symbol or '', 'position': currency.position},
            'kpis': {
                'mrr': round(mrr, 2), 'arr': round(mrr * 12, 2), 'active': active_count,
                'paused': len(paused), 'new': new_count, 'churned': churn_count,
                'churn_mrr': round(-_sum('3_churn'), 2),
                'arpu': round(mrr / active_count, 2) if active_count else 0,
                'expected_revenue': round(sum(s['expected_revenue'] for s in active), 2),
                'avg_length': avg_len,
                'churn_rate': round(churn_count / (active_count + churn_count) * 100, 1) if (active_count + churn_count) else 0.0,
                'expansion_mrr': round(_sum('1_expansion'), 2),
                'payment_issues': payment_issues,
                'renewing_soon': renewing_soon,
            },
            'swimlane': swimlane,
            'mrr_trend': {'labels': trend_labels, 'data': trend_data},
            'subs_trend': {'labels': trend_labels, 'data': subs_count},
            'movement': {'labels': ['New', 'Expansion', 'Contraction', 'Churn'],
                         'data': [_sum('0_creation'), _sum('1_expansion'), _sum('2_contraction'), _sum('3_churn')]},
            'movement_trend': {'labels': trend_labels, 'new': mv_new, 'churned': mv_churn},
            'by_plan': {'labels': [plan_names[k] for k, _v in plan_items],
                        'data': [round(v, 2) for _k, v in plan_items],
                        'ids': [k for k, _v in plan_items]},
            'top_customers': {'labels': [cust_names[k] for k, _v in top],
                              'data': [round(v, 2) for _k, v in top],
                              'ids': [k for k, _v in top]},
            'filter_options': {
                'plans': self.env['codeerts.subscription.plan'].search_read([], ['name']),
                'teams': self.env['crm.team'].search_read([], ['name']),
                'users': self.env['res.users'].search_read([('share', '=', False)], ['name']),
            },
            'filters': {'date_from': date_from, 'date_to': date_to,
                        'plan_id': plan_id, 'team_id': team_id, 'user_id': user_id},
        }
