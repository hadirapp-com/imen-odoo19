from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

DIRECTIONS = [
    ('rfq_to_quotation', 'RFQ to Quotation (buyer product/tax -> seller product/tax)'),
    ('invoice_to_bill', 'Invoice to Bill (seller product/tax -> buyer product/tax)'),
]


class IntercompanyProductMapping(models.Model):
    _name = 'intercompany.product.mapping'
    _description = 'Intercompany Product Mapping'
    _order = 'route_id, direction, id'

    route_id = fields.Many2one(
        'intercompany.route', required=True, ondelete='cascade', index=True)
    direction = fields.Selection(DIRECTIONS, required=True, default='rfq_to_quotation')
    source_product_id = fields.Many2one(
        'product.product', string='Source Product', required=True,
        ondelete='cascade', index=True, check_company=False)
    target_product_id = fields.Many2one(
        'product.product', string='Target Product', required=True,
        ondelete='cascade', index=True, check_company=False)
    active = fields.Boolean(default=True)

    _product_mapping_uniq = models.Constraint(
        'unique(route_id, direction, source_product_id)',
        'Only one target product per source product, route and direction. '
        'Archive the existing mapping first.')

    @api.constrains('route_id', 'direction', 'source_product_id', 'target_product_id')
    def _check_company_consistency(self):
        for mapping in self:
            source_companies, target_companies = mapping.route_id._mapping_allowed_companies()
            if mapping.source_product_id.company_id and \
                    mapping.source_product_id.company_id not in source_companies:
                raise ValidationError(_(
                    'Source product %s does not belong to the source side of route %s.',
                    mapping.source_product_id.display_name, mapping.route_id.name))
            if mapping.target_product_id.company_id and \
                    mapping.target_product_id.company_id not in target_companies:
                raise ValidationError(_(
                    'Target product %s does not belong to the target side of route %s.',
                    mapping.target_product_id.display_name, mapping.route_id.name))
            if mapping.source_product_id == mapping.target_product_id and \
                    mapping.source_product_id.company_id:
                raise ValidationError(_('Cannot map a company-specific product to itself.'))


class IntercompanyTaxMapping(models.Model):
    _name = 'intercompany.tax.mapping'
    _description = 'Intercompany Tax Mapping'
    _order = 'route_id, direction, id'

    route_id = fields.Many2one(
        'intercompany.route', required=True, ondelete='cascade', index=True)
    direction = fields.Selection(DIRECTIONS, required=True, default='rfq_to_quotation')
    source_tax_id = fields.Many2one(
        'account.tax', string='Source Tax', required=True,
        ondelete='cascade', index=True, check_company=False)
    target_tax_id = fields.Many2one(
        'account.tax', string='Target Tax', required=True,
        ondelete='cascade', check_company=False)
    active = fields.Boolean(default=True)

    _tax_mapping_uniq = models.Constraint(
        'unique(route_id, direction, source_tax_id)',
        'Only one target tax per source tax, route and direction.')

    @api.constrains('route_id', 'direction', 'source_tax_id', 'target_tax_id')
    def _check_company_consistency(self):
        # Taxes are always company-specific, so this check is strict on purpose:
        # a wrong company on a tax mapping would create wrong accounting entries.
        for mapping in self:
            source_companies, target_companies = mapping.route_id._mapping_allowed_companies()
            if mapping.source_tax_id.company_id not in source_companies:
                raise ValidationError(_(
                    'Source tax %s must belong to the source side of route %s.',
                    mapping.source_tax_id.display_name, mapping.route_id.name))
            if mapping.target_tax_id.company_id not in target_companies:
                raise ValidationError(_(
                    'Target tax %s must belong to the target side of route %s.',
                    mapping.target_tax_id.display_name, mapping.route_id.name))
            if mapping.source_tax_id.company_id == mapping.target_tax_id.company_id:
                raise ValidationError(_('Source and target tax must belong to different companies.'))
