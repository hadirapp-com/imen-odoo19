from odoo import fields, models


class AccountReportExpression(models.Model):
    _inherit = 'account.report.expression'

    date_scope = fields.Selection(
        selection_add=[('aging', 'Aging (as of period end)')],
        ondelete={'aging': 'set default'})

    hpr_aging_from_days = fields.Integer(
        string="Aging: From (days overdue)",
        help="Used with date_scope 'aging': bucket of lines overdue more than this number of days.")
    hpr_aging_to_days = fields.Integer(
        string="Aging: To (days overdue)",
        help="Upper bound of the aging bucket (inclusive). from=to=0 means the 'not due yet' bucket.")
