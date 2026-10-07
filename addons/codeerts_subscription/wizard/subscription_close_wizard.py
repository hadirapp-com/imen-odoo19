from odoo import fields, models


class SubscriptionCloseWizard(models.TransientModel):
    _name = 'codeerts.subscription.close.wizard'
    _description = 'Close Subscription Wizard'

    order_id = fields.Many2one('sale.order', string="Subscription", required=True, ondelete='cascade')
    close_reason_id = fields.Many2one(
        'codeerts.subscription.close.reason', string="Close Reason", required=True)
    closing_mode = fields.Selection(
        selection=[
            ('immediate', 'Immediately'),
            ('end_of_period', 'At End of Current Billing Period'),
        ],
        string="Closing", default='immediate', required=True)
    next_invoice_date = fields.Date(related='order_id.next_invoice_date', readonly=True)

    def action_close(self):
        self.ensure_one()
        order = self.order_id
        if self.closing_mode == 'end_of_period' and order.next_invoice_date:
            # Stay active until the current paid period ends; the expiration cron churns it then.
            order.write({
                'close_reason_id': self.close_reason_id.id,
                'end_date': order.next_invoice_date,
            })
        else:
            order._subscription_close(self.close_reason_id)
        return {'type': 'ir.actions.act_window_close'}
