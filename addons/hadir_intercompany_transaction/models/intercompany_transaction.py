import hashlib
import json
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

SYNC_STATES = [
    ('draft', 'Draft (Quotation not created)'),
    ('quotation_created', 'Quotation Created'),
    ('quotation_sent', 'Quotation Sent'),
    ('so_confirmed', 'Sales Order Confirmed'),
    ('partially_invoiced', 'Partially Invoiced'),
    ('fully_invoiced', 'Fully Invoiced'),
    ('error', 'Error'),
    ('cancelled', 'Cancelled'),
]


class IntercompanyTransaction(models.Model):
    _name = 'intercompany.transaction'
    _description = 'Intercompany Transaction'
    _inherit = ['mail.thread']
    _order = 'id desc'

    # The bridge is the only object readable by both companies:
    # company_id is not set and a global record rule restricts visibility to
    # users of the source or target company. All cross-company information is
    # stored here as plain snapshots written by the sync engine (never live
    # related fields, which would trigger cross-company AccessError).

    name = fields.Char(required=True, default='New', copy=False)
    route_id = fields.Many2one(
        'intercompany.route', string='Route', required=True, ondelete='restrict')
    source_company_id = fields.Many2one(
        'res.company', string='Source Company (Buyer)', readonly=True, index=True)
    target_company_id = fields.Many2one(
        'res.company', string='Target Company (Seller)', readonly=True, index=True)

    source_po_id = fields.Many2one(
        'purchase.order', string='Source RFQ', required=True,
        ondelete='restrict', index=True, check_company=False, copy=False)
    target_so_id = fields.Many2one(
        'sale.order', string='Target Sales Order',
        ondelete='restrict', index=True, check_company=False, copy=False)

    sync_state = fields.Selection(
        SYNC_STATES, string='Sync State', default='draft', tracking=True, copy=False)

    # Snapshots (plain columns, engine-written)
    source_reference = fields.Char(string='Source Ref (RFQ)', readonly=True, copy=False)
    target_reference = fields.Char(string='Target Ref (SO)', readonly=True, copy=False)
    source_currency_id = fields.Many2one('res.currency', string='Source Currency', readonly=True)
    target_currency_id = fields.Many2one('res.currency', string='Target Currency', readonly=True)
    source_amount_total = fields.Monetary(
        string='Source Total', currency_field='source_currency_id', readonly=True)
    target_amount_total = fields.Monetary(
        string='Target Total', currency_field='target_currency_id', readonly=True)
    source_amount_tax = fields.Monetary(
        string='Source Tax', currency_field='source_currency_id', readonly=True)
    target_amount_tax = fields.Monetary(
        string='Target Tax', currency_field='target_currency_id', readonly=True)
    source_amount_untaxed = fields.Monetary(
        string='Source Untaxed', currency_field='source_currency_id', readonly=True)
    target_amount_untaxed = fields.Monetary(
        string='Target Untaxed', currency_field='target_currency_id', readonly=True)
    exchange_rate = fields.Float(
        digits=(12, 6), readonly=True, help='Target currency units per source currency unit '
        'at snapshot time (1.0 when the currencies are identical).')

    integration_key = fields.Char(readonly=True, copy=False, index=True)
    last_sync_date = fields.Datetime(readonly=True, copy=False)
    last_sync_user_id = fields.Many2one('res.users', readonly=True, copy=False)
    sync_error = fields.Text(readonly=True, copy=False, tracking=True)
    retry_count = fields.Integer(default=0, copy=False)
    active = fields.Boolean(default=True)

    line_ids = fields.One2many(
        'intercompany.transaction.line', 'transaction_id', string='Snapshot Lines',
        copy=False)
    revision_ids = fields.One2many(
        'intercompany.quotation.revision', 'transaction_id', string='Quotation Revisions',
        copy=False)
    move_link_ids = fields.One2many(
        'intercompany.move.link', 'transaction_id', string='Invoice Links', copy=False)
    log_ids = fields.One2many('intercompany.sync.log', 'transaction_id', string='Sync Log')

    move_link_count = fields.Integer(compute='_compute_move_link_count')

    can_open_source_documents = fields.Boolean(compute='_compute_can_open_documents')
    can_open_target_documents = fields.Boolean(compute='_compute_can_open_documents')

    _source_po_uniq = models.Constraint(
        'unique(source_po_id)',
        'This RFQ already has an intercompany transaction.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'intercompany.transaction') or 'New'
        return super().create(vals_list)

    @api.depends('move_link_ids')
    def _compute_move_link_count(self):
        for tx in self:
            tx.move_link_count = len(tx.move_link_ids)

    def _compute_can_open_documents(self):
        for tx in self:
            companies = self.env.companies
            tx.can_open_source_documents = tx.source_company_id in companies
            tx.can_open_target_documents = tx.target_company_id in companies

    # ------------------------------------------------------------------
    # Engine helpers
    # ------------------------------------------------------------------

    def _sudo_write(self, vals):
        """Bridge bookkeeping (sync states, snapshots, errors) runs with sudo on
        purpose: it must never fail because of ACL timing and users only ever
        get read access to the bridge. Business documents are never touched here."""
        return self.sudo().write(dict(vals, last_sync_date=fields.Datetime.now(),
                                      last_sync_user_id=self.env.uid))

    def _log(self, operation, result='success', document_type='rfq',
             source_doc_ref=False, target_doc_ref=False, error_message=False,
             duration_ms=False, move_link=False):
        Log = self.env['intercompany.sync.log'].sudo()
        Log.create([{
            'transaction_id': tx.id,
            'move_link_id': move_link.id if move_link else False,
            'user_id': self.env.uid,
            'source_company_id': tx.source_company_id.id,
            'target_company_id': tx.target_company_id.id,
            'document_type': document_type,
            'source_doc_ref': source_doc_ref or '',
            'target_doc_ref': target_doc_ref or '',
            'operation': operation,
            'result': result,
            'error_message': error_message or '',
            'duration_ms': int(duration_ms or 0),
            'retry_count': tx.retry_count,
        } for tx in self])

    def _copy_attachments(self, source_record, target_record, target_company=False):
        """Copy-on-sync of user attachments. Odoo's filestore is content-addressed
        (sha1), so this never duplicates binary data - only attachment records.
        Attachments tied to binary fields (res_field set) are skipped."""
        Attachment = self.env['ir.attachment'].sudo()
        existing_names = {
            att.name for att in target_record.sudo().attachment_ids
        } if target_record.id else set()
        for attachment in source_record.sudo().attachment_ids.filtered(
                lambda a: not a.res_field and a.name not in existing_names):
            Attachment.create({
                'name': attachment.name,
                'datas': attachment.datas,
                'mimetype': attachment.mimetype,
                'res_model': target_record._name,
                'res_id': target_record.id,
                'company_id': target_company.id if target_company else False,
            })

    # ------------------------------------------------------------------
    # RFQ -> Quotation engine
    # ------------------------------------------------------------------

    @api.model
    def _resolve_target_product(self, route, direction, product):
        """Return (product|None, matched_by|error message)."""
        if not product:
            return None, _('Line has no product.')
        _source_ok, target_ok = route.with_context(
            intercompany_direction=direction)._mapping_allowed_companies()
        if not product.company_id or product.company_id in target_ok:
            return product, 'shared'
        mapping = self.env['intercompany.product.mapping'].sudo().search([
            ('route_id', '=', route.id),
            ('direction', '=', direction),
            ('active', '=', True),
            ('source_product_id', '=', product.id),
        ], limit=1)
        if mapping:
            return mapping.target_product_id, 'mapped'
        if not route.product_mapping_required and product.default_code:
            candidate = self.env['product.product'].sudo().search([
                ('default_code', '=', product.default_code),
                ('company_id', 'in', [False, target_ok.id]),
            ], limit=2)
            if len(candidate) == 1:
                return candidate, 'code'
        return None, _(
            'No product mapping for "%(product)s" (route %(route)s, direction %(direction)s).',
            product=product.display_name, route=route.name, direction=direction)

    def _map_taxes(self, route, direction, taxes):
        """Return (mapped taxes, missing taxes list)."""
        TaxMapping = self.env['intercompany.tax.mapping'].sudo()
        mapped, missing = self.env['account.tax'], self.env['account.tax']
        for tax in taxes:
            target = TaxMapping.search([
                ('route_id', '=', route.id),
                ('direction', '=', direction),
                ('active', '=', True),
                ('source_tax_id', '=', tax.id),
            ], limit=1)
            if target:
                mapped += target.target_tax_id
            else:
                missing += tax
        return mapped, missing

    @api.model
    def _collect_purchase_order_errors(self, po, route):
        """Collect every mapping problem before anything is created."""
        errors = []
        lines = po.order_line.filtered(lambda l: not l.display_type)
        if not lines:
            errors.append(_('The RFQ has no product lines.'))
        for line in lines:
            target_product, info = self._resolve_target_product(
                route, 'rfq_to_quotation', line.product_id)
            if not target_product:
                errors.append(_('Line "%s": %s', line.display_name, info))
            _mapped, missing = self._map_taxes(route, 'rfq_to_quotation', line.taxes_id)
            if missing and route.tax_mapping_required:
                errors.append(_('Line "%s": unmapped tax(es): %s',
                                line.display_name,
                                ', '.join(missing.mapped('name'))))
        return errors

    def _snapshot_purchase_order(self):
        """Fill source-side snapshots from the RFQ (engine/sudo context)."""
        po = self.source_po_id.sudo()
        lines = po.order_line.filtered(lambda l: not l.display_type)
        line_vals = [{
            'sequence': line.sequence,
            'source_product_name': line.product_id.display_name or line.name or '',
            'source_default_code': line.product_id.default_code or '',
            'source_uom': line.product_uom.name or '',
            'source_qty': line.product_qty,
            'source_price_unit': line.price_unit,
            'source_tax_desc': ', '.join(line.taxes_id.mapped('name')),
            'source_subtotal': line.price_subtotal,
        } for line in lines]
        self.line_ids.sudo().unlink()
        self.sudo().write({
            'source_reference': po.name,
            'source_currency_id': po.currency_id.id,
            'source_amount_total': po.amount_total,
            'source_amount_tax': po.amount_tax,
            'source_amount_untaxed': po.amount_untaxed,
            'target_currency_id': po.currency_id.id,
            'exchange_rate': 1.0,
            'integration_key': 'ICT-PO-%s' % po.id,
            'line_ids': [fields.Command.create(vals) for vals in line_vals],
        })
        self._copy_attachments(po, self)

    def _resolve_payment_term(self, term, target_company):
        if term and (not term.company_id or term.company_id == target_company):
            return term
        return self.route_id.default_payment_term_id or term

    def _prepare_quotation_vals(self):
        self.ensure_one()
        po = self.source_po_id.sudo()
        route = self.route_id
        target_company = self.target_company_id
        lines = po.order_line.filtered(lambda l: not l.display_type)
        order_lines = []
        for line in lines:
            target_product, _info = self._resolve_target_product(
                route, 'rfq_to_quotation', line.product_id)
            mapped_taxes, missing = self._map_taxes(route, 'rfq_to_quotation', line.taxes_id)
            order_lines.append(fields.Command.create({
                'product_id': target_product.id,
                'name': (line.name or target_product.display_name or '').strip(),
                'product_uom_qty': line.product_qty,
                'price_unit': line.price_unit,
                'tax_id': [fields.Command.set(mapped_taxes.ids)],
                'sequence': line.sequence,
            }))
            if missing and not route.tax_mapping_required:
                self._log('create_quotation', result='info', document_type='quotation',
                          error_message=_('Non-strict route: skipped unmapped tax(es) %s on line %s',
                                          ', '.join(missing.mapped('name')), line.display_name))
        return {
            'partner_id': po.partner_id.id,
            'company_id': target_company.id,
            'currency_id': po.currency_id.id,
            'client_order_ref': po.name,
            'origin': po.name,
            'commitment_date': po.date_planned or False,
            'payment_term_id': self._resolve_payment_term(
                po.payment_term_id, target_company).id or False,
            'intercompany_transaction_id': self.id,
            'order_line': order_lines,
        }

    def _create_quotation(self):
        """Create the native sales quotation in the target company. Must be called
        inside a savepoint: on exception nothing of the quotation survives.
        Document creation runs as the seller integration user - never sudo."""
        self.ensure_one()
        route = self.route_id
        user = route.target_user_id
        company = self.target_company_id
        SaleOrder = self.env['sale.order'].with_user(user).with_company(company)
        quotation = SaleOrder.create(self._prepare_quotation_vals())
        self._snapshot_quotation(quotation)
        return quotation

    def _snapshot_quotation(self, quotation):
        """Fill target-side snapshots from the quotation (engine/sudo context)."""
        so = quotation.sudo()
        tx_lines = self.line_ids.sudo().sorted('sequence')
        so_lines = so.order_line.filtered(lambda l: not l.display_type).sorted('sequence')
        for tx_line, so_line in zip(tx_lines, so_lines):
            tx_line.write({
                'target_product_name': so_line.product_id.display_name or '',
                'target_uom': so_line.product_uom.name or '',
                'target_qty': so_line.product_uom_qty,
                'target_price_unit': so_line.price_unit,
                'target_tax_desc': ', '.join(so_line.tax_id.mapped('name')),
                'target_subtotal': so_line.price_subtotal,
            })
        rate = 1.0
        if so.currency_id != self.source_currency_id:
            rate = self.source_currency_id.sudo()._get_conversion_rate(
                self.source_currency_id, so.currency_id,
                so.company_id, fields.Date.context_today(self))
        self._sudo_write({
            'target_so_id': so.id,
            'target_reference': so.name,
            'target_currency_id': so.currency_id.id,
            'target_amount_total': so.amount_total,
            'target_amount_tax': so.amount_tax,
            'target_amount_untaxed': so.amount_untaxed,
            'exchange_rate': rate,
        })

    def _sync_state_from_documents(self):
        """Derive the bridge state from the native document states. Never stores
        duplicated workflow data - only reads it (engine/sudo context)."""
        self.ensure_one()
        so = self.target_so_id.sudo()
        links = self.move_link_ids.sudo()
        if not so:
            return
        if so.state == 'cancel':
            if all(link.state in ('cancelled',) for link in links) or not links:
                self._sudo_write({'sync_state': 'cancelled'})
            return
        if so.state != 'sale':
            return
        if not links:
            self._sudo_write({'sync_state': 'so_confirmed'})
            return
        active_links = links.filtered(lambda l: l.state != 'cancelled')
        if not active_links:
            self._sudo_write({'sync_state': 'cancelled'})
        elif all(link.state == 'posted' for link in active_links):
            self._sudo_write({'sync_state': 'fully_invoiced'})
        else:
            self._sudo_write({'sync_state': 'partially_invoiced'})

    def action_sync_now(self):
        """Manual / cron retry. Reuses the existing bridge and integration key:
        idempotent by design."""
        for tx in self:
            if tx.target_so_id or tx.sync_state not in ('draft', 'error'):
                continue
            errors = self._collect_purchase_order_errors(tx.source_po_id, tx.route_id)
            if errors:
                raise UserError('\n'.join(errors))
            tx._snapshot_purchase_order()
            started = time.monotonic()
            try:
                with self.env.cr.savepoint():
                    quotation = tx._create_quotation()
            except UserError:
                raise
            except Exception as e:
                duration = (time.monotonic() - started) * 1000
                tx.sudo().write({
                    'sync_state': 'error',
                    'sync_error': str(e),
                    'retry_count': tx.retry_count + 1,
                })
                tx._log('create_quotation', result='failed', document_type='quotation',
                        source_doc_ref=tx.source_reference,
                        error_message=str(e), duration_ms=duration)
                tx.sudo().message_post(body=_('Intercompany quotation failed: %s', e))
                continue
            duration = (time.monotonic() - started) * 1000
            tx._sudo_write({
                'sync_state': 'quotation_created',
                'sync_error': False,
                'retry_count': 0,
            })
            tx._log('create_quotation', document_type='quotation',
                    source_doc_ref=tx.source_reference,
                    target_doc_ref=quotation.name, duration_ms=duration)
            tx.sudo().message_post(body=_(
                'Sales quotation %s created in %s.',
                quotation.name, tx.target_company_id.name))

    def action_retry(self):
        self.action_sync_now()

    def action_open_source_po(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': self.source_po_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_target_so(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.target_so_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_move_links(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice Links'),
            'res_model': 'intercompany.move.link',
            'view_mode': 'list,form',
            'domain': [('transaction_id', '=', self.id)],
            'context': {'default_transaction_id': self.id},
        }

    def action_open_sync_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Log'),
            'res_model': 'intercompany.sync.log',
            'view_mode': 'list,form',
            'domain': [('transaction_id', '=', self.id)],
        }

    # ------------------------------------------------------------------
    # Quotation revision snapshots
    # ------------------------------------------------------------------

    def _snapshot_quotation_revision(self, note=False):
        """Called when the seller sends the quotation. Content-hash dedup keeps
        only real revisions (locked design: no native quotation revisioning)."""
        self.ensure_one()
        so = self.target_so_id
        if not so:
            return False
        so_sudo = so.sudo()
        lines = [{
            'product': line.product_id.display_name or '',
            'code': line.product_id.default_code or '',
            'qty': line.product_uom_qty,
            'uom': line.product_uom.name or '',
            'price_unit': line.price_unit,
            'taxes': ', '.join(line.tax_id.mapped('name')),
            'subtotal': line.price_subtotal,
        } for line in so_sudo.order_line.filtered(lambda l: not l.display_type)]
        payload = json.dumps({
            'partner': so_sudo.partner_id.display_name,
            'currency': so_sudo.currency_id.name,
            'amount_total': so_sudo.amount_total,
            'lines': lines,
        }, sort_keys=True, default=str)
        content_hash = hashlib.sha256(payload.encode()).hexdigest()
        Revision = self.env['intercompany.quotation.revision'].sudo()
        existing = Revision.search([
            ('transaction_id', '=', self.id),
            ('content_hash', '=', content_hash),
        ], limit=1)
        if existing:
            return existing
        revision = Revision.create({
            'transaction_id': self.id,
            'content_hash': content_hash,
            'line_snapshot': payload,
            'amount_total': so_sudo.amount_total,
            'currency_id': so_sudo.currency_id.id,
            'note': note or '',
        })
        count = Revision.search_count([('transaction_id', '=', self.id)])
        revision.write({'revision_seq': count})
        self._snapshot_quotation(so)
        self._log('revise_quotation', document_type='quotation',
                  source_doc_ref=self.source_reference,
                  target_doc_ref=so_sudo.name)
        return revision

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------

    def _cron_retry(self):
        transactions = self.sudo().search([
            ('sync_state', '=', 'error'),
            ('target_so_id', '=', False),
            ('retry_count', '<', 10),
        ], order='retry_count asc', limit=50)
        for tx in transactions:
            try:
                tx.action_sync_now()
            except Exception as e:
                tx.sudo().write({
                    'retry_count': tx.retry_count + 1,
                    'sync_error': str(e),
                })
                tx._log('retry', result='failed', document_type='rfq',
                        source_doc_ref=tx.source_reference,
                        error_message=str(e))


class IntercompanyTransactionLine(models.Model):
    _name = 'intercompany.transaction.line'
    _description = 'Intercompany Transaction Line (snapshot)'
    _order = 'sequence, id'

    # Pure snapshot columns (no cross-company related fields): both companies
    # can read them without AccessError and list views stay cheap.

    transaction_id = fields.Many2one(
        'intercompany.transaction', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    source_product_name = fields.Char(string='Source Product')
    source_default_code = fields.Char(string='Source Code')
    target_product_name = fields.Char(string='Target Product')
    source_uom = fields.Char(string='Source UoM')
    target_uom = fields.Char(string='Target UoM')
    source_qty = fields.Float(string='Source Qty', digits='Product Unit of Measure')
    target_qty = fields.Float(string='Target Qty', digits='Product Unit of Measure')
    source_price_unit = fields.Monetary(
        string='Source Unit Price', currency_field='source_currency_id')
    target_price_unit = fields.Monetary(
        string='Target Unit Price', currency_field='target_currency_id')
    source_tax_desc = fields.Char(string='Source Taxes')
    target_tax_desc = fields.Char(string='Target Taxes')
    source_subtotal = fields.Monetary(
        string='Source Subtotal', currency_field='source_currency_id')
    target_subtotal = fields.Monetary(
        string='Target Subtotal', currency_field='target_currency_id')
    source_currency_id = fields.Many2one(
        related='transaction_id.source_currency_id')
    target_currency_id = fields.Many2one(
        related='transaction_id.target_currency_id')


class IntercompanyQuotationRevision(models.Model):
    _name = 'intercompany.quotation.revision'
    _description = 'Intercompany Quotation Revision (snapshot)'
    _order = 'transaction_id, revision_seq, id'

    transaction_id = fields.Many2one(
        'intercompany.transaction', required=True, ondelete='cascade', index=True)
    revision_seq = fields.Integer(string='#', default=1)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    content_hash = fields.Char(required=True)
    line_snapshot = fields.Json(string='Lines Snapshot')
    amount_total = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one('res.currency')
    note = fields.Char()
