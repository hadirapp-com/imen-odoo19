from odoo import _, api, fields, models
from odoo.exceptions import UserError

BOOKING_STATES = [
    ('draft', 'Draft'),
    ('confirmed', 'Confirmed'),
    ('document', 'Document Collection'),
    ('verification', 'Document Verification'),
    ('visa', 'Visa Processing'),
    ('ready', 'Ready for Departure'),
    ('departed', 'Departed'),
    ('returned', 'Returned'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]

PAYMENT_STATES = [
    ('unpaid', 'Unpaid'),
    ('partial', 'Partially Paid'),
    ('paid', 'Paid'),
    ('overdue', 'Overdue'),
]


class UmrahBooking(models.Model):
    _name = 'umrah.booking'
    _description = 'Umrah Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'departure_date desc, id desc'

    name = fields.Char(
        string='Booking Number', default=lambda self: _('New'),
        required=True, copy=False, readonly=True, index=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, index=True, tracking=True)
    sale_order_id = fields.Many2one(
        'sale.order', string='Sales Order',
        index=True, tracking=True, copy=False, ondelete='restrict')
    product_id = fields.Many2one(
        'product.template', string='Umrah Package',
        required=True, tracking=True, check_company=True,
        domain=[('is_umrah_package', '=', True)])
    departure_date = fields.Date(required=True, tracking=True, index=True)
    return_date = fields.Date(required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Coordinator', tracking=True,
        default=lambda self: self.env.user)
    project_id = fields.Many2one(
        'project.project', string='Project', readonly=True, copy=False, ondelete='set null')
    state = fields.Selection(
        selection=BOOKING_STATES, string='Status',
        default='draft', required=True, copy=False, index=True, tracking=True)

    pilgrim_ids = fields.One2many('umrah.pilgrim', 'booking_id', string='Pilgrims')
    pilgrim_count = fields.Integer(compute='_compute_counts', store=True)
    document_ids = fields.One2many('umrah.document', 'booking_id', string='Documents')
    document_count = fields.Integer(compute='_compute_counts', store=True)
    document_verified_count = fields.Integer(
        string='Verified Documents', compute='_compute_counts', store=True)
    document_progress = fields.Float(
        string='Document Progress', compute='_compute_document_progress', store=True)

    payment_status = fields.Selection(
        selection=PAYMENT_STATES, string='Payment Status',
        compute='_compute_payment', store=True)
    amount_total = fields.Monetary(compute='_compute_payment', store=True)
    amount_invoiced = fields.Monetary(compute='_compute_payment', store=True)
    amount_paid = fields.Monetary(compute='_compute_payment', store=True)
    amount_due = fields.Monetary(compute='_compute_payment', store=True)
    currency_id = fields.Many2one(
        related='company_id.currency_id', readonly=True)

    progress = fields.Float(
        string='Overall Progress', compute='_compute_progress', store=True)

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company, index=True)
    notes = fields.Text()

    @api.depends('pilgrim_ids', 'document_ids.state', 'document_ids.required')
    def _compute_counts(self):
        for booking in self:
            booking.pilgrim_count = len(booking.pilgrim_ids)
            booking.document_count = len(booking.document_ids)
            booking.document_verified_count = len(
                booking.document_ids.filtered(lambda d: d.state == 'verified'))

    @api.depends('document_ids.state', 'document_ids.required')
    def _compute_document_progress(self):
        for booking in self:
            required = booking.document_ids.filtered(
                lambda d: d.required and d.state != 'not_required')
            verified = required.filtered(lambda d: d.state == 'verified')
            booking.document_progress = (
                len(verified) / len(required) * 100.0) if required else 0.0

    @api.depends(
        'sale_order_id.amount_total',
        'sale_order_id.invoice_ids.payment_state',
        'sale_order_id.invoice_ids.state',
        'sale_order_id.invoice_ids.amount_total',
        'sale_order_id.invoice_ids.amount_residual',
        'sale_order_id.invoice_ids.invoice_date_due',
    )
    def _compute_payment(self):
        today = fields.Date.context_today(self)
        for booking in self:
            order = booking.sale_order_id
            booking.amount_total = order.amount_total if order else 0.0
            invoices = order.invoice_ids.filtered(
                lambda m: m.is_invoice() and m.state == 'posted') if order else self.env['account.move']
            booking.amount_invoiced = sum(invoices.mapped('amount_total'))
            booking.amount_paid = sum(
                invoices.mapped(lambda m: m.amount_total - m.amount_residual))
            booking.amount_due = booking.amount_total - booking.amount_paid
            overdue = any(
                invoice.invoice_date_due
                and invoice.invoice_date_due < today
                and invoice.payment_state in ('not_paid', 'partial')
                for invoice in invoices)
            if overdue:
                booking.payment_status = 'overdue'
            elif not order:
                booking.payment_status = 'unpaid'
            elif booking.amount_due <= 0 and booking.amount_invoiced > 0:
                booking.payment_status = 'paid'
            elif booking.amount_paid <= 0:
                booking.payment_status = 'unpaid'
            else:
                booking.payment_status = 'partial'

    @api.depends('document_progress', 'amount_total', 'amount_paid', 'state')
    def _compute_progress(self):
        for booking in self:
            if booking.state == 'completed':
                booking.progress = 100.0
                continue
            document_ratio = booking.document_progress / 100.0
            payment_ratio = (
                booking.amount_paid / booking.amount_total) if booking.amount_total else 1.0
            booking.progress = round(
                (document_ratio * 0.6 + payment_ratio * 0.4) * 100.0, 1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                sequence_date = fields.Date.to_date(vals.get('departure_date'))
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'umrah.booking', sequence_date=sequence_date) or _('New')
        bookings = super().create(vals_list)
        bookings._generate_document_checklist()
        return bookings

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active(self):
        for booking in self:
            if booking.state not in ('draft', 'cancelled'):
                raise UserError(_(
                    'Booking %(booking)s cannot be deleted: only draft or '
                    'cancelled bookings may be deleted.',
                    booking=booking.name))

    # -------------------------------------------------------------
    # Document checklist
    # -------------------------------------------------------------
    def _generate_document_checklist(self, pilgrims=None):
        Document = self.env['umrah.document']
        Template = self.env['umrah.document.template']
        default_template = False
        for booking in self:
            template = booking.product_id.document_template_id
            if not template:
                if not default_template:
                    default_template = Template._get_default_template(booking.company_id)
                template = default_template
            if not template:
                continue
            targets = booking.pilgrim_ids if pilgrims is None else \
                pilgrims.filtered(lambda p: p.booking_id == booking)
            if not targets:
                continue
            existing = Document.search([('pilgrim_id', 'in', targets.ids)])
            existing_map = {}
            for document in existing:
                existing_map.setdefault(document.pilgrim_id.id, set()).add(document.document_type_id.id)
            vals_list = [
                {
                    'pilgrim_id': pilgrim.id,
                    'document_type_id': line.document_type_id.id,
                    'required': line.required,
                }
                for pilgrim in targets
                for line in template.line_ids
                if line.document_type_id.id not in existing_map.get(pilgrim.id, set())
            ]
            if vals_list:
                Document.create(vals_list)

    def action_generate_checklist(self):
        self._generate_document_checklist()
        return True

    # -------------------------------------------------------------
    # State machine
    # -------------------------------------------------------------
    def action_confirm(self):
        invalid = self.filtered(lambda b: b.state != 'draft')
        if invalid:
            raise UserError(_('Only draft bookings can be confirmed: %s', ', '.join(invalid.mapped('name'))))
        for booking in self:
            if not booking.pilgrim_ids:
                raise UserError(_('Booking %s needs at least one pilgrim before confirmation.', booking.name))
            if booking.departure_date and booking.departure_date < fields.Date.context_today(self):
                raise UserError(_('Booking %s: departure date cannot be in the past.', booking.name))
        self.write({'state': 'confirmed'})
        self._generate_document_checklist()
        return True

    def _transition(self, from_state, to_state):
        wrong = self.filtered(lambda b: b.state != from_state)
        if wrong:
            raise UserError(_(
                'Booking %(bookings)s: expected status "%(expected)s".',
                bookings=', '.join(wrong.mapped('name')),
                expected=dict(BOOKING_STATES)[from_state]))
        self.write({'state': to_state})

    def action_start_documents(self):
        self._transition('confirmed', 'document')

    def action_set_verification(self):
        self._transition('document', 'verification')

    def action_ready_for_visa(self):
        self._transition('verification', 'visa')

    def action_set_ready(self):
        for booking in self:
            missing = booking.document_ids.filtered(
                lambda d: d.required and d.state not in ('verified', 'not_required'))
            if missing:
                raise UserError(_(
                    'Booking %(booking)s cannot be set ready: %(count)s required '
                    'document(s) are not verified yet.',
                    booking=booking.name, count=len(missing)))
            # Phase 2: also require every visa approved when visa records exist
        self._transition('visa', 'ready')
        self.pilgrim_ids.filtered(lambda p: p.state == 'registered').write({'state': 'ready'})

    def action_set_departed(self):
        self._transition('ready', 'departed')
        self.pilgrim_ids.write({'state': 'departed'})

    def action_set_returned(self):
        self._transition('departed', 'returned')
        self.pilgrim_ids.write({'state': 'returned'})

    def action_set_completed(self):
        self._transition('returned', 'completed')

    def action_cancel(self):
        if self.filtered(lambda b: b.state == 'completed'):
            raise UserError(_('Completed bookings cannot be cancelled.'))
        self.filtered(lambda b: b.state != 'cancelled').write({'state': 'cancelled'})
        self.pilgrim_ids.write({'state': 'cancelled'})
        return True

    def action_reset_draft(self):
        wrong = self.filtered(lambda b: b.state != 'cancelled')
        if wrong:
            raise UserError(_('Only cancelled bookings can be reset to draft.'))
        self.write({'state': 'draft'})
        self.pilgrim_ids.write({'state': 'registered'})
        return True

    # -------------------------------------------------------------
    # Operations
    # -------------------------------------------------------------
    def action_create_project(self):
        Project = self.env['project.project']
        for booking in self.filtered(lambda b: not b.project_id and b.state not in ('draft', 'cancelled')):
            booking.project_id = Project.create({
                'name': _('Umrah %s - %s', booking.name, booking.partner_id.display_name),
                'partner_id': booking.partner_id.id,
                'company_id': booking.company_id.id,
                'date_start': booking.departure_date,
                'date': booking.return_date,
            })
        return True

    def action_open_project(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('No project linked to this booking yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project'),
            'res_model': 'project.project',
            'view_mode': 'form',
            'res_id': self.project_id.id,
        }

    def _schedule_deduped_activity(self, summary, note):
        """Create an activity unless an open one with the same summary exists."""
        self.ensure_one()
        Activity = self.env['mail.activity']
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        domain = [
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('summary', '=', summary),
        ]
        if todo:
            domain.append(('activity_type_id', '=', todo.id))
        if Activity.search_count(domain):
            return False
        user_id = self.user_id.id or self.sale_order_id.user_id.id or self.create_uid.id
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=user_id,
            summary=summary,
            note=note,
            date_deadline=fields.Date.context_today(self),
        )
        return True

    @api.model
    def _cron_missing_documents(self):
        """Daily: warn about required documents still missing close to departure."""
        today = fields.Date.context_today(self)
        horizon = fields.Date.add(today, days=30)
        bookings = self.search([
            ('state', 'in', ('document', 'verification', 'visa')),
            ('departure_date', '<=', horizon),
        ])
        for booking in bookings:
            missing = booking.document_ids.filtered(
                lambda d: d.required and d.state not in ('verified', 'not_required'))
            if not missing:
                continue
            days_left = (booking.departure_date - today).days if booking.departure_date else 0
            note = _(
                '%(count)s required document(s) still incomplete for %(pilgrims)s '
                'pilgrim(s) - %(days)s day(s) before departure (%(departure)s).',
                count=len(missing), pilgrims=booking.pilgrim_count,
                days=days_left, departure=booking.departure_date)
            booking._schedule_deduped_activity(_('Missing documents'), note)

    # -------------------------------------------------------------
    # Smart buttons
    # -------------------------------------------------------------
    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_('No sales order linked to this booking.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Order'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def action_view_pilgrims(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pilgrims'),
            'res_model': 'umrah.pilgrim',
            'view_mode': 'list,form',
            'domain': [('booking_id', '=', self.id)],
            'context': {'default_booking_id': self.id},
        }

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documents'),
            'res_model': 'umrah.document',
            'view_mode': 'list,form',
            'domain': [('booking_id', '=', self.id)],
        }

    def action_view_invoices(self):
        self.ensure_one()
        invoices = self.sale_order_id.invoice_ids.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund')) if self.sale_order_id else self.env['account.move']
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoices.ids)],
            'context': {'default_move_type': 'out_invoice'},
        }
        if len(invoices) == 1:
            action.update({'res_id': invoices[0].id, 'view_mode': 'form'})
        return action

    def action_view_payments(self):
        self.ensure_one()
        invoices = self.sale_order_id.invoice_ids.filtered(
            lambda m: m.is_invoice() and m.state == 'posted') if self.sale_order_id else self.env['account.move']
        payments = self.env['account.payment'].search(
            [('invoice_ids', 'in', invoices.ids)]) if invoices else self.env['account.payment']
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payments.ids)],
        }
        if len(payments) == 1:
            action.update({'res_id': payments[0].id, 'view_mode': 'form'})
        return action
