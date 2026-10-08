import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LINK_STATES = [
    ('pending', 'Pending'),
    ('draft', 'Vendor Bill Draft'),
    ('posted', 'Vendor Bill Posted'),
    ('error', 'Error'),
    ('cancelled', 'Cancelled'),
]

PAYMENT_STATES = [
    ('none', 'Not Synced'),
    ('not_paid', 'Not Paid'),
    ('in_payment', 'In Payment'),
    ('paid', 'Paid'),
    ('reversed', 'Reversed'),
]


class IntercompanyMoveLink(models.Model):
    _name = 'intercompany.move.link'
    _description = 'Intercompany Move Link'
    _inherit = ['mail.thread']
    _order = 'id desc'

    # One link per source accounting document (customer invoice or credit note
    # of the seller). unique(source_move_id) makes bill creation idempotent:
    # double hooks, manual retries and concurrent cron runs cannot duplicate it.

    transaction_id = fields.Many2one(
        'intercompany.transaction', string='Transaction',
        required=True, ondelete='restrict', index=True)
    link_type = fields.Selection(
        [('invoice', 'Customer Invoice'), ('credit_note', 'Credit Note')],
        required=True, default='invoice')
    source_move_id = fields.Many2one(
        'account.move', string='Source Invoice', required=True,
        ondelete='restrict', index=True, check_company=False, copy=False)
    target_move_id = fields.Many2one(
        'account.move', string='Target Vendor Bill',
        ondelete='set null', index=True, check_company=False, copy=False,
        help='Cleared automatically if the draft bill is deleted; the link '
             'then goes to Error and can be retried.')

    state = fields.Selection(
        LINK_STATES, default='pending', required=True, tracking=True, copy=False)

    # Payment mirror (informational only - never copies payment entries)
    payment_state = fields.Selection(PAYMENT_STATES, default='none', copy=False, tracking=True)
    payment_date = fields.Date(copy=False)
    payment_reference = fields.Char(copy=False)

    # Snapshots
    source_document_name = fields.Char(string='Source Document', copy=False)
    target_document_name = fields.Char(string='Target Document', copy=False)
    source_currency_id = fields.Many2one('res.currency', copy=False)
    target_currency_id = fields.Many2one('res.currency', copy=False)
    source_amount_total = fields.Monetary(
        string='Source Total', currency_field='source_currency_id', copy=False)
    target_amount_total = fields.Monetary(
        string='Target Total', currency_field='target_currency_id', copy=False)
    exchange_rate = fields.Float(digits=(12, 6), copy=False)

    integration_key = fields.Char(copy=False, index=True)
    sync_error = fields.Text(copy=False, tracking=True)
    retry_count = fields.Integer(default=0, copy=False)
    last_sync_date = fields.Datetime(copy=False)

    company_id_source = fields.Many2one(
        related='transaction_id.source_company_id', string='Buyer Company')
    company_id_target = fields.Many2one(
        related='transaction_id.target_company_id', string='Seller Company')

    can_open_source_documents = fields.Boolean(compute='_compute_can_open_documents')
    can_open_target_documents = fields.Boolean(compute='_compute_can_open_documents')

    _source_move_uniq = models.Constraint(
        'unique(source_move_id)',
        'This invoice already has an intercompany link.')

    def _compute_can_open_documents(self):
        companies = self.env.companies
        for link in self:
            link.can_open_source_documents = link._source_company() in companies
            link.can_open_target_documents = link._target_company() in companies

    def _source_company(self):
        self.ensure_one()
        return self.transaction_id.target_company_id

    def _target_company(self):
        self.ensure_one()
        return self.transaction_id.source_company_id

    def _route(self):
        return self.transaction_id.route_id

    # ------------------------------------------------------------------
    # Invoice -> Vendor Bill engine
    # ------------------------------------------------------------------

    @api.model
    def _find_for_move(self, move):
        return self.search([('source_move_id', '=', move.id)], limit=1)

    def _validate_invoice(self):
        """Collect mapping problems before creating the bill."""
        self.ensure_one()
        invoice = self.source_move_id.sudo()
        route = self._route()
        errors = []
        lines = invoice.invoice_line_ids.filtered(lambda l: not l.display_type)
        if not lines:
            errors.append(_('The invoice has no product lines.'))
        for line in lines:
            if not line.product_id:
                errors.append(_(
                    'Line "%s": invoice lines without product are not supported '
                    'by the intercompany bridge.', line.name or '/'))
            else:
                product, info = self.transaction_id._resolve_target_product(
                    route, 'invoice_to_bill', line.product_id)
                if not product:
                    errors.append(_('Line "%s": %s', line.name or '/', info))
            _mapped, missing = self.transaction_id._map_taxes(
                route, 'invoice_to_bill', line.tax_ids)
            if missing and route.tax_mapping_required:
                errors.append(_('Line "%s": unmapped tax(es): %s',
                                line.name or '/', ', '.join(missing.mapped('name'))))
        return errors

    def _prepare_bill_vals(self):
        self.ensure_one()
        invoice = self.source_move_id.sudo()
        tx = self.transaction_id
        route = self._route()
        is_refund = self.link_type == 'credit_note'
        original_bill = invoice.reversed_entry_id.sudo() if is_refund else False
        lines = invoice.invoice_line_ids.filtered(lambda l: not l.display_type)
        bill_lines = []
        for line in lines:
            product, _info = tx._resolve_target_product(route, 'invoice_to_bill', line.product_id)
            mapped_taxes, _missing = tx._map_taxes(route, 'invoice_to_bill', line.tax_ids)
            bill_lines.append(fields.Command.create({
                'product_id': product.id if line.product_id else False,
                'name': (line.name or '').strip(),
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [fields.Command.set(mapped_taxes.ids)],
                'sequence': line.sequence,
            }))
        term = tx._resolve_payment_term(
            invoice.invoice_payment_term_id, tx.source_company_id)
        narration = _(
            'Intercompany: %(doc_type)s %(invoice)s from %(seller)s '
            '(bridge %(bridge)s, RFQ %(rfq)s).',
            doc_type=_('Credit note') if is_refund else _('Invoice'),
            invoice=invoice.name or '', seller=tx.target_company_id.name,
            bridge=tx.name, rfq=tx.source_reference or '-')
        vals = {
            'move_type': 'in_refund' if is_refund else 'in_invoice',
            'partner_id': tx.target_company_id.partner_id.id,
            'ref': invoice.name or '',
            'invoice_origin': invoice.name or '',
            'invoice_date': invoice.invoice_date,
            'currency_id': invoice.currency_id.id,
            'invoice_payment_term_id': term.id or False,
            'narration': narration,
            'invoice_line_ids': bill_lines,
        }
        if is_refund and original_bill:
            vals['reversed_entry_id'] = original_bill.id
        return vals

    def _create_target_bill(self):
        """Create the native vendor bill (draft) in the buyer company as the
        buyer integration user. Call inside a savepoint for atomicity."""
        self.ensure_one()
        route = self._route()
        tx = self.transaction_id
        company = tx.source_company_id
        user = route._integration_user_for(company)
        AccountMove = self.env['account.move'].with_user(user).with_company(company)
        bill = AccountMove.create(self._prepare_bill_vals())
        # source invoice documents travel with the bill for buyer accounting review
        self.transaction_id._copy_attachments(
            self.source_move_id, bill, company)
        auto_post = route.vendor_bill_auto_post
        if auto_post:
            bill.with_user(user).action_post()
        rate = 1.0
        if bill.sudo().currency_id != self.source_currency_id:
            rate = self.source_currency_id.sudo()._get_conversion_rate(
                self.source_currency_id, bill.sudo().currency_id,
                company, fields.Date.context_today(self))
        self.sudo().write({
            'target_move_id': bill.id,
            'target_document_name': bill.name or bill.ref or '',
            'target_currency_id': bill.currency_id.id,
            'target_amount_total': bill.amount_total,
            'exchange_rate': rate,
            'state': 'posted' if auto_post else 'draft',
            'sync_error': False,
            'last_sync_date': fields.Datetime.now(),
        })
        return bill

    def _process_posted_invoice(self):
        """Entry point called from account.move.action_post. Idempotent:
        an existing link short-circuits the whole flow."""
        self.ensure_one()
        invoice = self.source_move_id
        started = time.monotonic()
        errors = self._validate_invoice()
        if errors:
            message = '\n'.join(errors)
            self.sudo().write({
                'state': 'error',
                'sync_error': message,
                'retry_count': self.retry_count + 1,
            })
            self.transaction_id._log(
                'create_bill', result='failed',
                document_type='credit_note' if self.link_type == 'credit_note' else 'invoice',
                source_doc_ref=self.source_document_name,
                error_message=message, duration_ms=(time.monotonic() - started) * 1000,
                move_link=self)
            return False
        try:
            with self.env.cr.savepoint():
                bill = self._create_target_bill()
        except Exception as e:
            message = str(e)
            self.sudo().write({
                'state': 'error',
                'sync_error': message,
                'retry_count': self.retry_count + 1,
            })
            self.transaction_id._log(
                'create_bill', result='failed',
                document_type='credit_note' if self.link_type == 'credit_note' else 'invoice',
                source_doc_ref=self.source_document_name,
                error_message=message, duration_ms=(time.monotonic() - started) * 1000,
                move_link=self)
            return False
        self.transaction_id._log(
            'create_bill',
            document_type='credit_note' if self.link_type == 'credit_note' else 'invoice',
            source_doc_ref=self.source_document_name,
            target_doc_ref=bill.name or bill.ref or '',
            duration_ms=(time.monotonic() - started) * 1000,
            move_link=self)
        self.transaction_id._sync_state_from_documents()
        return True

    def action_retry(self):
        """Manual retry. Validation problems raise so the user sees them right
        away; creation problems are recorded on the link."""
        for link in self:
            if link.state != 'error' or link.target_move_id:
                continue
            errors = link._validate_invoice()
            if errors:
                raise UserError('\n'.join(errors))
            link._process_posted_invoice()
        self.transaction_id._sync_state_from_documents()

    def _sync_payment_status(self):
        """Mirror payment information from the source invoice. No account.payment
        is ever created or copied between companies."""
        for link in self:
            invoice = link.source_move_id.sudo()
            if not link._route().payment_status_sync_enabled:
                continue
            payment_date = False
            try:
                widget = invoice.invoice_payments_widget or {}
                dates = [c.get('date') for c in widget.get('content', []) if c.get('date')]
                payment_date = max(dates) if dates else False
            except Exception:
                payment_date = False
            link.sudo().write({
                'payment_state': invoice.payment_state or 'none',
                'payment_date': payment_date,
                'payment_reference': invoice.payment_reference or invoice.ref or '',
                'last_sync_date': fields.Datetime.now(),
            })
            link.transaction_id._log(
                'sync_payment', result='info', document_type='payment_status',
                source_doc_ref=link.source_document_name,
                target_doc_ref=link.target_document_name, move_link=link)

    def _on_source_cancelled(self):
        """The source invoice was cancelled or reset to draft. Draft bills may
        be cancelled automatically; posted bills are never touched - the buyer
        must issue a credit note (accounting history stays intact)."""
        for link in self.filtered(lambda l: l.state in ('draft', 'pending', 'error')):
            route = link._route()
            bill = link.target_move_id
            if bill and bill.sudo().state == 'draft' and route.auto_cancel_draft_bill:
                bill.with_user(route._integration_user_for(
                    link.transaction_id.source_company_id)).button_cancel()
                link.sudo().write({
                    'state': 'cancelled',
                    'sync_error': _('Source invoice cancelled; draft bill cancelled.'),
                })
            elif bill and bill.sudo().state == 'posted':
                link.sudo().write({
                    'state': 'error',
                    'sync_error': _(
                        'Source invoice was cancelled while the vendor bill is already '
                        'posted. Issue a credit note instead of cancelling.'),
                })
            else:
                link.sudo().write({
                    'state': 'cancelled',
                    'sync_error': _('Source invoice cancelled before bill creation.'),
                })
            link.transaction_id._log(
                'cancel', result='info',
                document_type='credit_note' if link.link_type == 'credit_note' else 'invoice',
                source_doc_ref=link.source_document_name,
                target_doc_ref=link.target_document_name,
                error_message=link.sync_error, move_link=link)
        for tx in self.transaction_id:
            tx._sync_state_from_documents()

    def action_open_source_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.source_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_target_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.target_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
