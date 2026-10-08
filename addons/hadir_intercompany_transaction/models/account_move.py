from odoo import _, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    intercompany_move_link_id = fields.Many2one(
        'intercompany.move.link', string='Intercompany Link',
        copy=False, index=True, check_company=False)

    # ------------------------------------------------------------------
    # Posting hook
    # ------------------------------------------------------------------

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.move_type in ('out_invoice', 'out_credit_note') and move.state == 'posted':
                try:
                    move._intercompany_process_posted()
                except Exception as e:  # never break the native posting
                    move._intercompany_record_hook_failure(e)
        return res

    def _intercompany_record_hook_failure(self, exception):
        self.ensure_one()
        self.sudo().message_post(body=_(
            'Intercompany bridge error after posting: %s\n'
            'Open Intercompany > Transactions to retry.', exception))
        self.env['intercompany.sync.log'].sudo().create({
            'user_id': self.env.uid,
            'document_type': 'invoice',
            'source_doc_ref': self.name or '',
            'operation': 'create_bill',
            'result': 'failed',
            'error_message': str(exception),
        })

    def _intercompany_find_transaction(self):
        """Resolve the bridge chain for this invoice (engine/sudo reads)."""
        self.ensure_one()
        move = self.sudo()
        orders = move.invoice_line_ids.sale_line_ids.order_id
        bridged = orders.filtered('intercompany_transaction_id')
        if bridged:
            return bridged[0].intercompany_transaction_id
        if move.move_type == 'out_credit_note' and move.reversed_entry_id:
            origin_link = self.env['intercompany.move.link'].sudo()._find_for_move(
                move.reversed_entry_id)
            if origin_link:
                return origin_link.transaction_id
        return self.env['intercompany.transaction']

    def _intercompany_process_posted(self):
        """Called after a customer invoice / credit note is posted. Creates the
        move link once (idempotent via unique(source_move_id)) and, if the
        route enables it, the draft vendor bill in the buyer company."""
        self.ensure_one()
        Link = self.env['intercompany.move.link']
        link = Link._find_for_move(self)
        if link:
            if link.state == 'pending':
                link._process_posted_invoice()
            elif link.state == 'cancelled' and not link.target_move_id:
                # invoice was reset to draft (bill auto-cancelled) then re-posted
                link.sudo().write({'state': 'pending', 'sync_error': False})
                link._process_posted_invoice()
            return  # draft/posted/error: nothing to do on re-post
        tx = self._intercompany_find_transaction()
        if not tx:
            return  # not an intercompany invoice
        route = tx.route_id
        if not route.auto_create_vendor_bill:
            return
        try:
            with self.env.cr.savepoint():
                link = Link.sudo().create({
                    'transaction_id': tx.id,
                    'link_type': 'credit_note' if self.move_type == 'out_credit_note' else 'invoice',
                    'source_move_id': self.id,
                    'source_document_name': self.name or '',
                    'source_currency_id': self.currency_id.id,
                    'source_amount_total': self.amount_total,
                    'integration_key': 'ICT-MOVE-%s' % self.id,
                })
        except Exception:
            link = Link._find_for_move(self)  # concurrent creation lost the race
            if not link:
                raise
        self.sudo().write({'intercompany_move_link_id': link.id})
        link._process_posted_invoice()

    # ------------------------------------------------------------------
    # State / payment mirror hooks
    # ------------------------------------------------------------------

    def write(self, vals):
        res = super().write(vals)
        if not vals.keys() & {'state', 'payment_state'}:
            return res
        for move in self:
            if move.move_type != 'out_invoice' and not (
                    move.move_type == 'out_credit_note' and vals.get('state') in ('cancel', 'draft')):
                continue
            link = move.intercompany_move_link_id or \
                self.env['intercompany.move.link']._find_for_move(move)
            if not link:
                continue
            if 'payment_state' in vals and move.move_type == 'out_invoice':
                if link._route().payment_status_sync_enabled and \
                        link.state in ('draft', 'posted'):
                    link._sync_payment_status()
            if vals.get('state') in ('cancel', 'draft'):
                link._on_source_cancelled()
        return res

    def action_view_intercompany(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Intercompany Link'),
            'res_model': 'intercompany.move.link',
            'res_id': self.intercompany_move_link_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
