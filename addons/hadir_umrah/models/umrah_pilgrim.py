from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

GENDERS = [
    ('male', 'Male'),
    ('female', 'Female'),
    ('other', 'Other'),
]

PILGRIM_STATES = [
    ('registered', 'Registered'),
    ('ready', 'Ready'),
    ('departed', 'Departed'),
    ('returned', 'Returned'),
    ('cancelled', 'Cancelled'),
]


class UmrahPilgrim(models.Model):
    _name = 'umrah.pilgrim'
    _description = 'Umrah Pilgrim'
    _inherit = ['mail.thread']
    _order = 'booking_id, id'
    _rec_name = 'full_name'

    booking_id = fields.Many2one(
        'umrah.booking', string='Booking', required=True, index=True, ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Related Contact', index=True,
        help='Contact record of the pilgrim. Required later for the jamaah portal login.')
    full_name = fields.Char(string='Full Name', required=True, tracking=True)
    nik = fields.Char(
        string='NIK (National ID)', index=True,
        groups='hadir_umrah.group_umrah_user,hadir_umrah.group_umrah_visa')
    birth_place = fields.Char(string='Place of Birth')
    birth_date = fields.Date(string='Date of Birth')
    gender = fields.Selection(selection=GENDERS, required=True, default='male')
    phone = fields.Char()
    email = fields.Char()
    address = fields.Text()

    passport_name = fields.Char(
        string='Name as in Passport',
        help='Name spelled exactly as printed on the passport.')
    passport_number = fields.Char(string='Passport Number', index=True, tracking=True)
    passport_issue_date = fields.Date(string='Passport Issue Date')
    passport_expiry_date = fields.Date(string='Passport Expiry Date', index=True, tracking=True)
    passport_issue_place = fields.Char(string='Passport Issue Place')
    passport_expiry_status = fields.Selection(
        selection=[
            ('valid', 'Valid'),
            ('expiring', 'Expiring Soon'),
            ('expired', 'Expired'),
        ],
        string='Passport Status',
        compute='_compute_passport_expiry_status',
        store=True)

    state = fields.Selection(
        selection=PILGRIM_STATES, string='Status',
        default='registered', required=True, tracking=True)
    document_ids = fields.One2many('umrah.document', 'pilgrim_id', string='Documents')
    document_required_count = fields.Integer(
        string='Required Documents', compute='_compute_document_progress', store=True)
    document_verified_count = fields.Integer(
        string='Verified Documents', compute='_compute_document_progress', store=True)
    document_progress = fields.Float(
        string='Document Progress', compute='_compute_document_progress', store=True)
    company_id = fields.Many2one(
        related='booking_id.company_id', store=True, index=True, readonly=True)
    notes = fields.Text()

    @api.depends('document_ids.state', 'document_ids.required')
    def _compute_document_progress(self):
        for pilgrim in self:
            required = pilgrim.document_ids.filtered(
                lambda d: d.required and d.state != 'not_required')
            verified = required.filtered(lambda d: d.state == 'verified')
            pilgrim.document_required_count = len(required)
            pilgrim.document_verified_count = len(verified)
            pilgrim.document_progress = (
                len(verified) / len(required) * 100.0) if required else 0.0

    @api.depends('passport_expiry_date', 'booking_id.return_date')
    def _compute_passport_expiry_status(self):
        today = fields.Date.context_today(self)
        for pilgrim in self:
            expiry = pilgrim.passport_expiry_date
            if not expiry:
                pilgrim.passport_expiry_status = False
                continue
            if expiry < today:
                pilgrim.passport_expiry_status = 'expired'
            else:
                # Saudi regulation: passport must still be valid 6 months after arrival
                limit = fields.Date.add(pilgrim.booking_id.return_date or today, months=6)
                pilgrim.passport_expiry_status = 'expiring' if expiry <= limit else 'valid'

    @api.constrains('nik', 'booking_id')
    def _check_nik_unique_per_booking(self):
        for pilgrim in self:
            if not pilgrim.nik:
                continue
            duplicate = self.search_count([
                ('booking_id', '=', pilgrim.booking_id.id),
                ('nik', '=', pilgrim.nik),
                ('id', '!=', pilgrim.id),
            ])
            if duplicate:
                raise ValidationError(_(
                    'NIK %(nik)s is already used by another pilgrim in booking %(booking)s.',
                    nik=pilgrim.nik, booking=pilgrim.booking_id.name))

    @api.constrains('birth_date')
    def _check_birth_date(self):
        today = fields.Date.context_today(self)
        for pilgrim in self:
            if pilgrim.birth_date and pilgrim.birth_date > today:
                raise ValidationError(_('Date of birth cannot be in the future.'))

    @api.constrains('passport_issue_date', 'passport_expiry_date')
    def _check_passport_dates(self):
        for pilgrim in self:
            if (pilgrim.passport_issue_date and pilgrim.passport_expiry_date
                    and pilgrim.passport_expiry_date <= pilgrim.passport_issue_date):
                raise ValidationError(_('Passport expiry date must be after the issue date.'))

    @api.model_create_multi
    def create(self, vals_list):
        pilgrims = super().create(vals_list)
        pilgrims._auto_create_partner()
        for booking in pilgrims.booking_id:
            if booking.state not in ('draft', 'cancelled'):
                booking._generate_document_checklist(
                    pilgrims.filtered(lambda p: p.booking_id == booking))
        return pilgrims

    def _auto_create_partner(self):
        Partner = self.env['res.partner']
        missing = self.filtered(lambda p: not p.partner_id)
        partners = Partner.create([{
            'name': pilgrim.full_name,
            'phone': pilgrim.phone,
            'email': pilgrim.email,
            'is_company': False,
            'customer_rank': 1,
        } for pilgrim in missing])
        for pilgrim, partner in zip(missing, partners):
            pilgrim.partner_id = partner.id
        return partners

    def action_create_partner(self):
        self._auto_create_partner()

    @api.model
    def _cron_check_passport_expiry(self):
        """Daily: one aggregated activity per booking for passports at risk."""
        pilgrims = self.search([
            ('passport_expiry_status', 'in', ('expiring', 'expired')),
            ('booking_id.state', 'not in', ('draft', 'cancelled', 'completed')),
        ])
        for booking in pilgrims.booking_id:
            affected = pilgrims.filtered(lambda p: p.booking_id == booking)
            expired = affected.filtered(lambda p: p.passport_expiry_status == 'expired')
            names = ', '.join(affected[:10].mapped('full_name'))
            if len(affected) > 10:
                names += _(', and %s more', len(affected) - 10)
            note = _(
                '%(count)s pilgrim(s) have a passport expiring within 6 months of '
                'return or already expired: %(names)s',
                count=len(affected), names=names)
            if expired:
                note += '\n' + _('Already expired: %s', ', '.join(expired.mapped('full_name')))
            booking._schedule_deduped_activity(_('Passport expiry risk'), note)
