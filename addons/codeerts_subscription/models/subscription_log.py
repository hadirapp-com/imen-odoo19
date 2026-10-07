from odoo import fields, models


class SubscriptionLog(models.Model):
    """MRR-change event log. One row per lifecycle event (creation / expansion /
    contraction / churn / transfer). Powers the MRR & churn analytics."""
    _name = 'codeerts.subscription.log'
    _description = 'Subscription MRR Log'
    _order = 'event_date desc, id desc'

    order_id = fields.Many2one(
        'sale.order', string="Subscription", required=True, ondelete='cascade', index=True)
    event_type = fields.Selection(
        selection=[
            ('0_creation', 'New'),
            ('1_expansion', 'Expansion'),
            ('2_contraction', 'Contraction'),
            ('3_churn', 'Churn'),
            ('4_transfer', 'Transfer'),
        ],
        string="Event", required=True, index=True)
    event_date = fields.Date(string="Date", default=fields.Date.context_today, index=True)
    recurring_monthly = fields.Monetary(
        string="MRR", currency_field='currency_id',
        help="Monthly recurring revenue of the subscription right after this event.")
    amount_signed = fields.Monetary(
        string="MRR Change", currency_field='currency_id',
        help="Signed change in MRR caused by this event (positive = expansion).")
    currency_id = fields.Many2one('res.currency', string="Currency")
    plan_id = fields.Many2one('codeerts.subscription.plan', string="Plan")
    partner_id = fields.Many2one('res.partner', string="Customer")
    user_id = fields.Many2one('res.users', string="Salesperson")
    team_id = fields.Many2one('crm.team', string="Sales Team")
    company_id = fields.Many2one('res.company', string="Company")
