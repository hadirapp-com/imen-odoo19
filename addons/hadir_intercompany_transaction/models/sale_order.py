from odoo import _, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    intercompany_transaction_id = fields.Many2one(
        'intercompany.transaction', string='Intercompany Transaction',
        copy=False, index=True, check_company=False,
        help='Set automatically when this quotation was created by the '
             'intercompany bridge from a purchase RFQ.')

    intercompany_sync_state = fields.Selection(
        related='intercompany_transaction_id.sync_state',
        string='Intercompany Status')
    intercompany_source_ref = fields.Char(
        related='intercompany_transaction_id.source_reference',
        string='Source RFQ')

    def action_confirm(self):
        res = super().action_confirm()
        for so in self.filtered('intercompany_transaction_id'):
            tx = so.intercompany_transaction_id
            tx._log('confirm_so', document_type='sale_order',
                    source_doc_ref=tx.source_reference,
                    target_doc_ref=so.name)
            tx._sudo_write({'sync_state': 'so_confirmed', 'target_reference': so.name})
            tx.sudo().message_post(body=_(
                'Sales order confirmed (%s). The buyer can follow the status from '
                'the intercompany bridge.', so.name))
        return res

    def action_quotation_sent(self):
        res = super().action_quotation_sent()
        for so in self.filtered('intercompany_transaction_id'):
            tx = so.intercompany_transaction_id
            try:
                tx._snapshot_quotation_revision(note=_('Sent to buyer'))
                if tx.sync_state in ('draft', 'quotation_created'):
                    tx._sudo_write({'sync_state': 'quotation_sent'})
            except Exception as e:
                # Never block the native quotation mailing because of the bridge
                tx._log('revise_quotation', result='failed', document_type='quotation',
                        source_doc_ref=tx.source_reference,
                        target_doc_ref=so.name, error_message=str(e))
        return res

    def action_cancel(self):
        res = super().action_cancel()
        for so in self.filtered('intercompany_transaction_id'):
            tx = so.intercompany_transaction_id
            posted_links = tx.move_link_ids.filtered(
                lambda l: l.state in ('draft', 'posted'))
            new_state = 'partially_invoiced' if posted_links else 'cancelled'
            tx._sudo_write({'sync_state': new_state})
            tx._log('cancel', document_type='sale_order',
                    source_doc_ref=tx.source_reference,
                    target_doc_ref=so.name,
                    error_message=_('Sales order cancelled.') if not posted_links else _(
                        'Sales order cancelled while vendor bills exist.'))
        return res

    def action_view_intercompany(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Intercompany Transaction'),
            'res_model': 'intercompany.transaction',
            'res_id': self.intercompany_transaction_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
