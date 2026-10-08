from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class IntercompanyRoute(models.Model):
    _name = 'intercompany.route'
    _description = 'Intercompany Route'
    _order = 'sequence, id'

    # A route represents the trading relationship between two companies.
    # source = purchasing company, target = selling company.
    # It serves both legs: RFQ (source) -> Quotation (target) and
    # Customer Invoice (target) -> Vendor Bill (source).

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    source_company_id = fields.Many2one(
        'res.company', string='Source Company (Buyer)', required=True, ondelete='cascade')
    target_company_id = fields.Many2one(
        'res.company', string='Target Company (Seller)', required=True, ondelete='cascade')

    purchase_to_sale_enabled = fields.Boolean(
        string='RFQ to Sales Quotation', default=False,
        help='Enable the bridge when a purchase RFQ is sent from the source company '
             'to a vendor that is the target company.')
    auto_create_quotation = fields.Boolean(
        default=True, help='Create the sales quotation immediately when the RFQ is sent.')
    auto_create_vendor_bill = fields.Boolean(
        string='Invoice to Vendor Bill', default=False,
        help='Create a draft vendor bill in the source company when a customer invoice '
             'of the bridged sales order is posted in the target company.')
    vendor_bill_auto_post = fields.Boolean(
        string='Auto-post Vendor Bill', default=False,
        help='Leave disabled to let the source company accounting review and post '
             'the vendor bill manually (recommended).')
    auto_cancel_draft_bill = fields.Boolean(
        string='Auto-cancel Draft Bill', default=True,
        help='When the source customer invoice is cancelled or reset to draft, '
             'automatically cancel the counterpart vendor bill if it is still in draft.')
    payment_status_sync_enabled = fields.Boolean(
        string='Payment Status Sync', default=True,
        help='Mirror payment status, date and reference of the customer invoice onto the '
             'vendor bill link. No payment entry is ever copied between companies.')

    target_user_id = fields.Many2one(
        'res.users', string='Integration User (Seller)', ondelete='restrict',
        help='Internal user of the target company used to create quotations. '
             'Must not be a portal/public user.')
    source_user_id = fields.Many2one(
        'res.users', string='Integration User (Buyer)', ondelete='restrict',
        help='Internal user of the source company used to create vendor bills.')

    product_mapping_required = fields.Boolean(
        default=False,
        help='When enabled, only shared products or explicit product mappings are accepted. '
             'When disabled, an auto-match by internal reference is also accepted and logged.')
    tax_mapping_required = fields.Boolean(
        string='Strict Tax Mapping', default=True,
        help='When enabled, every source tax must have an explicit mapping for the flow '
             'to proceed. Documents are never created with guessed taxes.')

    default_payment_term_id = fields.Many2one(
        'account.payment.term', string='Default Payment Term (Fallback)',
        help='Used when the payment term of the source document is not usable '
             'in the target company.')

    product_mapping_ids = fields.One2many('intercompany.product.mapping', 'route_id')
    tax_mapping_ids = fields.One2many('intercompany.tax.mapping', 'route_id')

    _companies_differ = models.Constraint(
        'CHECK (source_company_id <> target_company_id)',
        'Source and target company must be different.')
    _company_pair_uniq = models.Constraint(
        'unique(source_company_id, target_company_id)',
        'A route already exists for this company pair.')

    @api.constrains('source_company_id', 'target_company_id')
    def _check_companies(self):
        for route in self:
            if route.source_company_id == route.target_company_id:
                raise ValidationError(_('Source and target company must be different.'))
            duplicate = self.search_count([
                ('id', '!=', route.id),
                ('source_company_id', '=', route.target_company_id.id),
                ('target_company_id', '=', route.source_company_id.id),
            ])
            if duplicate:
                raise ValidationError(_(
                    'A route already exists in the reverse direction between these companies. '
                    'One route serves both legs.'))
            for company, other in (
                    (route.source_company_id, route.target_company_id),
                    (route.target_company_id, route.source_company_id)):
                partner = company.partner_id
                if partner and partner.company_id and partner.company_id != other:
                    raise ValidationError(_(
                        'The partner of %(company)s is restricted to company '
                        '%(partner_company)s, so the other company cannot use it on its '
                        'documents. Clear the Company field on the partner %(partner)s to '
                        'share it across companies.',
                        company=company.name, partner_company=partner.company_id.name,
                        partner=partner.display_name))

    @api.constrains('purchase_to_sale_enabled', 'auto_create_vendor_bill',
                    'target_user_id', 'source_user_id')
    def _check_integration_users(self):
        for route in self:
            if route.purchase_to_sale_enabled and route.auto_create_quotation:
                if not route.target_user_id:
                    raise ValidationError(_(
                        'Route "%s" needs an integration user of the target (seller) '
                        'company to create quotations.', route.name))
            if route.auto_create_vendor_bill:
                if not route.source_user_id:
                    raise ValidationError(_(
                        'Route "%s" needs an integration user of the source (buyer) '
                        'company to create vendor bills.', route.name))
            for user, company in (
                    (route.target_user_id, route.target_company_id),
                    (route.source_user_id, route.source_company_id)):
                if user and (user.share or company not in user.company_ids):
                    raise ValidationError(_(
                        'Integration user "%s" must be an internal user belonging to '
                        'company "%s".', user.name, company.name))

    def _integration_user_for(self, company):
        self.ensure_one()
        if company == self.source_company_id:
            return self.source_user_id
        if company == self.target_company_id:
            return self.target_user_id
        raise ValidationError(_(
            'Company %s is not part of route %s.', company.name, self.name))

    def _mapping_allowed_companies(self):
        """(allowed source companies, allowed target companies) per mapping direction."""
        self.ensure_one()
        if not self.env.context.get('intercompany_direction'):
            return (self.source_company_id | self.target_company_id,) * 2
        direction = self.env.context['intercompany_direction']
        if direction == 'rfq_to_quotation':
            return (self.source_company_id, self.target_company_id)
        return (self.target_company_id, self.source_company_id)

    @api.model
    def _find_for_purchase_order(self, purchase_order):
        """Route for an RFQ of the buyer company sent to the seller company partner."""
        return self.search([
            ('active', '=', True),
            ('purchase_to_sale_enabled', '=', True),
            ('source_company_id', '=', purchase_order.company_id.id),
            ('target_company_id.partner_id', '=', purchase_order.partner_id.id),
        ], limit=1)

    def _find_for_transaction(self, source_company, target_company):
        return self.search([
            ('active', '=', True),
            ('source_company_id', '=', source_company.id),
            ('target_company_id', '=', target_company.id),
        ], limit=1)
