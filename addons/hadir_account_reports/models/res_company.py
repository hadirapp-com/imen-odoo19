from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    hadir_is_head_office = fields.Boolean(
        string="Kantor Pusat (Konsolidasi)",
        help="Enable consolidated financial statements: this company acts as "
             "the head office and reports aggregate itself with the branches "
             "listed below.")
    hadir_branch_ids = fields.Many2many(
        'res.company', 'hadir_head_office_branch_rel',
        'head_office_id', 'branch_id', string="Daftar Cabang",
        help="Branch companies consolidated into this head office.")
    hadir_consolidation_company_ids = fields.Many2many(
        'res.company', compute='_compute_hadir_consolidation_company_ids',
        help="Head office first, then branches — the order matters because it "
             "is used as allowed_company_ids scope.")

    @api.depends('hadir_branch_ids')
    def _compute_hadir_consolidation_company_ids(self):
        for company in self:
            company.hadir_consolidation_company_ids = (
                company | company.hadir_branch_ids.sorted('name'))

    @api.constrains('hadir_branch_ids')
    def _check_hadir_branches(self):
        for company in self:
            for branch in company.hadir_branch_ids:
                if branch == company:
                    raise ValidationError(
                        _("A head office cannot list itself as a branch."))
                if branch.hadir_is_head_office:
                    raise ValidationError(
                        _("%(branch)s is itself a head office and cannot be a "
                          "branch of %(head)s.",
                          branch=branch.display_name,
                          head=company.display_name))
                other = self.search([
                    ('hadir_branch_ids', 'in', branch.ids),
                    ('id', '!=', company.id)], limit=1)
                if other:
                    raise ValidationError(
                        _("%(branch)s is already a branch of %(head)s.",
                          branch=branch.display_name,
                          head=other.display_name))
