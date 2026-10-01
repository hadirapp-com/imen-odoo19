from odoo import _, api, fields, models
from odoo.exceptions import UserError

DOCUMENT_STATES = [
    ('missing', 'Missing'),
    ('submitted', 'Submitted'),
    ('verification', 'In Verification'),
    ('verified', 'Verified'),
    ('rejected', 'Rejected'),
    ('expired', 'Expired'),
    ('not_required', 'Not Required'),
]


class UmrahDocument(models.Model):
    _name = 'umrah.document'
    _description = 'Umrah Pilgrim Document'
    _inherit = ['mail.thread']
    _order = 'pilgrim_id, document_type_id'
    _rec_name = 'document_type_id'

    pilgrim_id = fields.Many2one(
        'umrah.pilgrim', string='Pilgrim', required=True, index=True, ondelete='cascade')
    booking_id = fields.Many2one(
        related='pilgrim_id.booking_id', store=True, index=True, readonly=True)
    document_type_id = fields.Many2one(
        'umrah.document.type', string='Document Type', required=True, index=True)
    required = fields.Boolean(default=True, tracking=True)
    state = fields.Selection(
        selection=DOCUMENT_STATES,
        default='missing',
        required=True,
        index=True,
        tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Attachments',
        help='Scan or photo of the document.')
    submitted_date = fields.Date(readonly=True, copy=False)
    verified_date = fields.Date(readonly=True, copy=False)
    verified_by = fields.Many2one('res.users', string='Verified By', readonly=True, copy=False)
    reject_reason = fields.Char(tracking=True)
    expiry_date = fields.Date(index=True)
    company_id = fields.Many2one(
        related='pilgrim_id.company_id', store=True, readonly=True)

    _pilgrim_type_uniq = models.Constraint(
        'UNIQUE (pilgrim_id, document_type_id)',
        'This document type already exists for this pilgrim.')

    @api.onchange('document_type_id', 'pilgrim_id')
    def _onchange_default_expiry(self):
        if self.document_type_id.code == 'passport' and self.pilgrim_id and not self.expiry_date:
            self.expiry_date = self.pilgrim_id.passport_expiry_date

    def action_submit(self):
        for doc in self:
            if doc.state not in ('missing', 'rejected'):
                raise UserError(_('Only missing or rejected documents can be submitted.'))
            if not doc.attachment_ids:
                raise UserError(_('Attach a scan or photo before submitting "%s".', doc.document_type_id.name))
        self.write({
            'state': 'submitted',
            'submitted_date': fields.Date.context_today(self),
            'reject_reason': False,
        })

    def action_send_verification(self):
        for doc in self:
            if doc.state != 'submitted':
                raise UserError(_('Only submitted documents can be sent to verification.'))
        self.write({'state': 'verification'})

    def action_verify(self):
        for doc in self:
            if doc.state not in ('submitted', 'verification'):
                raise UserError(_('Only submitted or in-verification documents can be verified.'))
            if not doc.attachment_ids:
                raise UserError(_('Document "%s" has no attachment and cannot be verified.', doc.document_type_id.name))
        self.write({
            'state': 'verified',
            'verified_date': fields.Date.context_today(self),
            'verified_by': self.env.user.id,
        })

    def action_reject(self):
        for doc in self:
            if doc.state not in ('submitted', 'verification'):
                raise UserError(_('Only submitted or in-verification documents can be rejected.'))
            if not doc.reject_reason:
                raise UserError(_('Fill in the rejection reason before rejecting "%s".', doc.document_type_id.name))
        self.write({'state': 'rejected', 'verified_date': False, 'verified_by': False})

    def action_mark_not_required(self):
        self.write({'state': 'not_required', 'required': False})

    def action_reset(self):
        self.write({
            'state': 'missing',
            'submitted_date': False,
            'verified_date': False,
            'verified_by': False,
            'reject_reason': False,
        })

    @api.model
    def _cron_mark_expired(self):
        today = fields.Date.context_today(self)
        docs = self.search([
            ('expiry_date', '!=', False),
            ('expiry_date', '<', today),
            ('state', '=', 'verified'),
        ])
        docs.write({'state': 'expired'})
