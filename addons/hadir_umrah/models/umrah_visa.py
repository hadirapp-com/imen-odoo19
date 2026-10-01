from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

VISA_STATES = [
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('processing', 'Processing'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('expired', 'Expired'),
]


class UmrahVisa(models.Model):
    _name = 'umrah.visa'
    _description = 'Umrah Visa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'booking_id, pilgrim_id'
    _rec_name = 'visa_number'

    booking_id = fields.Many2one(
        'umrah.booking', string='Booking', required=True, index=True, ondelete='cascade')
    pilgrim_id = fields.Many2one(
        'umrah.pilgrim', string='Pilgrim', required=True, index=True, ondelete='cascade')
    # Snapshot of the passport used for the application; kept as a plain char
    # field (not related) because the passport can be renewed during processing.
    passport_number = fields.Char(
        string='Passport Number',
        index=True,
        groups='hadir_umrah.group_umrah_user,hadir_umrah.group_umrah_visa',
        tracking=True)
    visa_number = fields.Char(string='Visa Number', index=True, tracking=True)
    application_date = fields.Date(string='Application Date')
    submission_date = fields.Date(string='Submission Date', readonly=True, copy=False)
    approval_date = fields.Date(string='Approval Date', readonly=True, copy=False)
    expiry_date = fields.Date(string='Expiry Date')
    state = fields.Selection(
        selection=VISA_STATES, string='Status',
        default='draft', required=True, copy=False, index=True, tracking=True)
    state_label = fields.Char(
        string='Status Label', compute='_compute_state_label',
        help='Human-readable status, usable in notification templates '
             '(${object.state_label}).')
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Attachments',
        help='Visa scan or approval file.')
    notes = fields.Text()
    company_id = fields.Many2one(
        related='booking_id.company_id', store=True, index=True, readonly=True)

    _booking_pilgrim_uniq = models.Constraint(
        'UNIQUE (booking_id, pilgrim_id)',
        'This pilgrim already has a visa record on this booking.')

    @api.constrains('pilgrim_id', 'booking_id')
    def _check_pilgrim_belongs_to_booking(self):
        for visa in self:
            if visa.pilgrim_id.booking_id != visa.booking_id:
                raise ValidationError(_(
                    'Pilgrim %(pilgrim)s does not belong to booking %(booking)s.',
                    pilgrim=visa.pilgrim_id.full_name, booking=visa.booking_id.name))

    @api.onchange('pilgrim_id')
    def _onchange_pilgrim(self):
        if self.pilgrim_id and not self.passport_number:
            self.passport_number = self.pilgrim_id.passport_number

    @api.depends('state')
    def _compute_state_label(self):
        for visa in self:
            visa.state_label = dict(VISA_STATES).get(visa.state, visa.state)

    def action_notify_pilgrim(self):
        for visa in self:
            self.env['umrah.notification']._queue_event(
                'visa_update', visa.booking_id, pilgrims=visa.pilgrim_id, visa=visa)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Notifications'),
            'res_model': 'umrah.notification',
            'view_mode': 'list,form',
            'domain': [('visa_id', 'in', self.ids)],
        }

    def action_submit(self):
        for visa in self:
            if visa.state != 'draft':
                raise UserError(_('Only draft visas can be submitted.'))
        self.write({
            'state': 'submitted',
            'submission_date': fields.Date.context_today(self),
        })

    def action_process(self):
        for visa in self:
            if visa.state != 'submitted':
                raise UserError(_('Only submitted visas can move to processing.'))
        self.write({'state': 'processing'})

    def action_approve(self):
        for visa in self:
            if visa.state not in ('submitted', 'processing'):
                raise UserError(_('Only submitted or processing visas can be approved.'))
        self.write({
            'state': 'approved',
            'approval_date': fields.Date.context_today(self),
        })
        for visa in self:
            self.env['umrah.notification']._queue_event(
                'visa_update', visa.booking_id, pilgrims=visa.pilgrim_id, visa=visa)

    def action_reject(self):
        for visa in self:
            if visa.state not in ('submitted', 'processing'):
                raise UserError(_('Only submitted or processing visas can be rejected.'))
        self.write({'state': 'rejected', 'approval_date': False})

    def action_reset(self):
        self.write({
            'state': 'draft',
            'submission_date': False,
            'approval_date': False,
        })

    @api.model
    def _cron_mark_expired(self):
        """Daily: approved visas past their expiry date become expired."""
        today = fields.Date.context_today(self)
        visas = self.search([
            ('state', '=', 'approved'),
            ('expiry_date', '!=', False),
            ('expiry_date', '<', today),
        ])
        visas.write({'state': 'expired'})
        for booking in visas.booking_id:
            affected = visas.filtered(lambda v: v.booking_id == booking)
            booking._schedule_deduped_activity(_('Visa expired'), _(
                '%(count)s visa(s) reached their expiry date: %(names)s',
                count=len(affected),
                names=', '.join(affected.pilgrim_id.mapped('full_name'))))
