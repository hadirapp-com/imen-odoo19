from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountBudget(models.Model):
    _name = 'account.budget'
    _description = 'Budget'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(string='Start Date', required=True, tracking=True)
    date_to = fields.Date(string='End Date', required=True, tracking=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('cancel', 'Cancelled'),
         ('confirmed', 'Confirmed'), ('done', 'Done')],
        required=True, default='draft', tracking=True, copy=False)
    line_ids = fields.One2many('account.budget.line', 'budget_id', string='Budget Lines', copy=True)
    planned_amount = fields.Monetary(compute='_compute_totals', store=True)
    achieved_amount = fields.Monetary(compute='_compute_totals', store=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_from and budget.date_to and budget.date_from > budget.date_to:
                raise ValidationError(_("The budget start date must precede the end date."))

    @api.constrains('line_ids')
    def _check_lines(self):
        for budget in self:
            analytics = budget.line_ids.mapped('analytic_account_id')
            if len(analytics) != len(budget.line_ids):
                raise ValidationError(_("Each budget line must use a different analytic account."))

    @api.depends('line_ids.planned_amount', 'line_ids.achieved_amount')
    def _compute_totals(self):
        for budget in self:
            budget.planned_amount = sum(budget.line_ids.mapped('planned_amount'))
            budget.achieved_amount = sum(budget.line_ids.mapped('achieved_amount'))

    def action_confirm(self):
        self.filtered(lambda b: b.state == 'draft').write({'state': 'confirmed'})

    def action_done(self):
        self.filtered(lambda b: b.state == 'confirmed').write({'state': 'done'})

    def action_cancel(self):
        self.filtered(lambda b: b.state in ('draft', 'confirmed')).write({'state': 'cancel'})

    def action_draft(self):
        self.filtered(lambda b: b.state == 'cancel').write({'state': 'draft'})

    def unlink(self):
        if any(budget.state not in ('draft', 'cancel') for budget in self):
            raise ValidationError(_("Only draft or cancelled budgets can be deleted."))
        return super().unlink()


class AccountBudgetLine(models.Model):
    _name = 'account.budget.line'
    _description = 'Budget Line'

    budget_id = fields.Many2one('account.budget', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='budget_id.company_id', store=True)
    currency_id = fields.Many2one(related='budget_id.currency_id')
    name = fields.Char(compute='_compute_name')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account',
        required=True, check_company=True)
    planned_amount = fields.Monetary(required=True)
    achieved_amount = fields.Monetary(
        compute='_compute_achieved',
        help="Realized amount, from posted analytic lines within the budget "
             "dates. Analytic convention applies: costs are positive, "
             "revenues are negative.")
    achieved_percentage = fields.Float(compute='_compute_achieved')

    @api.depends('budget_id.name', 'analytic_account_id')
    def _compute_name(self):
        for line in self:
            line.name = f"{line.budget_id.name or ''} - {line.analytic_account_id.display_name or ''}"

    def _compute_achieved(self):
        AnalyticLine = self.env['account.analytic.line']
        for line in self:
            if not line.analytic_account_id or not line.budget_id.date_from:
                line.achieved_amount = 0.0
                line.achieved_percentage = 0.0
                continue
            column = line.analytic_account_id.plan_id._column_name()
            domain = [
                ('company_id', '=', line.company_id.id),
                ('date', '>=', line.budget_id.date_from),
                ('date', '<=', line.budget_id.date_to),
                (column, '=', line.analytic_account_id.id),
            ]
            groups = AnalyticLine._read_group(domain, [], ['amount:sum'])
            line.achieved_amount = groups[0][0] if groups and groups[0][0] else 0.0
            if line.planned_amount:
                line.achieved_percentage = line.achieved_amount / line.planned_amount * 100.0
            else:
                line.achieved_percentage = 0.0
