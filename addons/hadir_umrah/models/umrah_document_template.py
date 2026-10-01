from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class UmrahDocumentTemplate(models.Model):
    _name = 'umrah.document.template'
    _description = 'Umrah Document Template'

    name = fields.Char(required=True, translate=True)
    line_ids = fields.One2many(
        'umrah.document.template.line', 'template_id', string='Required Documents', copy=True)
    is_default = fields.Boolean(
        string='Default Template',
        help='Used to generate the checklist when a package has no template set.')
    note = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company')

    @api.constrains('is_default')
    def _check_single_default(self):
        for template in self.filtered('is_default'):
            domain = [('is_default', '=', True), ('id', '!=', template.id)]
            if template.company_id:
                domain += ['|', ('company_id', '=', False), ('company_id', '=', template.company_id.id)]
            if self.search_count(domain):
                raise ValidationError(_('Only one default document template is allowed per company.'))

    @api.model
    def _get_default_template(self, company=None):
        domain = [('is_default', '=', True)]
        if company:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        return self.search(domain, limit=1)


class UmrahDocumentTemplateLine(models.Model):
    _name = 'umrah.document.template.line'
    _description = 'Umrah Document Template Line'
    _order = 'id'
    _rec_name = 'document_type_id'

    template_id = fields.Many2one(
        'umrah.document.template', required=True, index=True, ondelete='cascade')
    document_type_id = fields.Many2one(
        'umrah.document.type', string='Document Type', required=True)
    required = fields.Boolean(default=True)
    note = fields.Char(translate=True)

    _type_uniq = models.Constraint(
        'UNIQUE (template_id, document_type_id)',
        'This document type is already in the template.')
