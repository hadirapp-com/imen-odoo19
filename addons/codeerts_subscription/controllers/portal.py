from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError


class SubscriptionPortal(CustomerPortal):

    def _subscription_domain(self, partner):
        return [
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ('progress', 'paused', 'renewed', 'churn')),
            ('partner_id', 'child_of', partner.commercial_partner_id.id),
        ]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'subscription_count' in counters:
            partner = request.env.user.partner_id
            values['subscription_count'] = request.env['sale.order'].search_count(
                self._subscription_domain(partner))
        return values

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_subscriptions(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        SaleOrder = request.env['sale.order']
        domain = self._subscription_domain(partner)
        total = SaleOrder.search_count(domain)
        pager = portal_pager(
            url='/my/subscriptions', total=total, page=page, step=self._items_per_page)
        subs = SaleOrder.search(
            domain, limit=self._items_per_page, offset=pager['offset'], order='date_order desc')
        values.update({
            'subscriptions': subs,
            'page_name': 'subscription',
            'pager': pager,
            'default_url': '/my/subscriptions',
        })
        return request.render('codeerts_subscription.portal_my_subscriptions', values)

    @http.route(['/my/subscriptions/<int:subscription_id>'],
                type='http', auth='public', website=True)
    def portal_subscription_page(self, subscription_id, access_token=None, **kw):
        try:
            sub_sudo = self._document_check_access('sale.order', subscription_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = {
            'subscription': sub_sudo,
            'page_name': 'subscription',
            'invoices': sub_sudo.invoice_ids.filtered(lambda m: m.state == 'posted'),
            'token': access_token,
        }
        return request.render('codeerts_subscription.portal_subscription_page', values)

    @http.route(['/my/subscriptions/<int:subscription_id>/close'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_subscription_close(self, subscription_id, access_token=None, **kw):
        try:
            sub_sudo = self._document_check_access('sale.order', subscription_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if sub_sudo.plan_id.user_closable and sub_sudo.subscription_state in ('progress', 'paused'):
            reason = request.env.ref(
                'codeerts_subscription.close_reason_other', raise_if_not_found=False)
            sub_sudo._subscription_close(close_reason=reason)
        return request.redirect('/my/subscriptions/%s' % subscription_id)

    @http.route(['/my/subscriptions/<int:subscription_id>/pause'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_subscription_pause(self, subscription_id, access_token=None, **kw):
        try:
            sub_sudo = self._document_check_access('sale.order', subscription_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if sub_sudo.plan_id.pausable and sub_sudo.subscription_state == 'progress':
            sub_sudo.action_subscription_pause()
        return request.redirect('/my/subscriptions/%s' % subscription_id)
