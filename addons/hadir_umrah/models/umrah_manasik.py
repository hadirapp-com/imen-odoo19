from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ATTENDANCE_STATES = [
    ('present', 'Present'),
    ('absent', 'Absent'),
    ('reschedule', 'Reschedule'),
]


def _float_to_hours_minutes(value):
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    return hours, minutes


class UmrahManasik(models.Model):
    _name = 'umrah.manasik'
    _description = 'Umrah Manasik Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(required=True, tracking=True)
    booking_id = fields.Many2one(
        'umrah.booking', string='Booking', required=True, index=True,
        tracking=True, ondelete='cascade')
    date = fields.Date(string='Date', required=True, index=True, tracking=True)
    start_time = fields.Float(string='Start Time', required=True, default=9.0)
    end_time = fields.Float(string='End Time', required=True, default=11.0)
    location = fields.Char()
    trainer_id = fields.Many2one(
        'res.partner', string='Trainer', tracking=True,
        domain=[('is_company', '=', False)])
    attendance_ids = fields.One2many(
        'umrah.manasik.attendance', 'manasik_id', string='Attendance')
    attendee_count = fields.Integer(compute='_compute_attendance', store=True)
    present_count = fields.Integer(compute='_compute_attendance', store=True)
    calendar_event_id = fields.Many2one(
        'calendar.event', string='Calendar Event',
        readonly=True, copy=False, ondelete='set null')
    company_id = fields.Many2one(
        related='booking_id.company_id', store=True, index=True, readonly=True)

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for manasik in self:
            if manasik.start_time < 0.0 or manasik.end_time > 24.0:
                raise ValidationError(_('Times must be between 0:00 and 24:00.'))
            if manasik.end_time <= manasik.start_time:
                raise ValidationError(_('End time must be after the start time.'))

    @api.constrains('attendance_ids')
    def _check_attendance_pilgrims(self):
        for manasik in self:
            wrong = manasik.attendance_ids.filtered(
                lambda line: line.pilgrim_id.booking_id != manasik.booking_id)
            if wrong:
                raise ValidationError(_(
                    'Pilgrim %(pilgrim)s does not belong to booking %(booking)s.',
                    pilgrim=wrong[0].pilgrim_id.full_name,
                    booking=manasik.booking_id.name))

    @api.depends('attendance_ids', 'attendance_ids.attendance')
    def _compute_attendance(self):
        for manasik in self:
            manasik.attendee_count = len(manasik.attendance_ids)
            manasik.present_count = len(
                manasik.attendance_ids.filtered(lambda line: line.attendance == 'present'))

    def action_fill_attendees(self):
        """Add every pilgrim of the booking that has no attendance line yet."""
        for manasik in self:
            existing = manasik.attendance_ids.pilgrim_id
            missing = manasik.booking_id.pilgrim_ids - existing
            manasik.write({'attendance_ids': [
                (0, 0, {'pilgrim_id': pilgrim.id}) for pilgrim in missing]})
        return True

    def action_mark_all_present(self):
        self.attendance_ids.filtered(
            lambda line: line.attendance != 'present').write({'attendance': 'present'})
        return True

    def _prepare_calendar_datetime(self, value):
        hours, minutes = _float_to_hours_minutes(value)
        return datetime.combine(self.date, time(hours, minutes))

    def action_open_calendar_event(self):
        self.ensure_one()
        if not self.calendar_event_id:
            raise ValidationError(_('No calendar event linked to this manasik yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Calendar Event'),
            'res_model': 'calendar.event',
            'view_mode': 'form',
            'res_id': self.calendar_event_id.id,
        }

    def action_schedule_calendar(self):
        self.ensure_one()
        if self.calendar_event_id:
            return self.action_open_calendar_event()
        partners = self.booking_id.user_id.partner_id
        if self.trainer_id:
            partners |= self.trainer_id
        partners |= self.attendance_ids.pilgrim_id.partner_id
        event = self.env['calendar.event'].create({
            'name': self.name,
            'start': self._prepare_calendar_datetime(self.start_time),
            'stop': self._prepare_calendar_datetime(self.end_time),
            'location': self.location or False,
            'description': _(
                'Manasik session for booking %(booking)s (%(pilgrims)s pilgrims).',
                booking=self.booking_id.name, pilgrims=self.attendee_count),
            'partner_ids': [(6, 0, partners.ids)],
            'res_model_id': self.env['ir.model']._get_id('umrah.manasik'),
            'res_id': self.id,
        })
        self.calendar_event_id = event.id
        return self.action_open_calendar_event()


class UmrahManasikAttendance(models.Model):
    _name = 'umrah.manasik.attendance'
    _description = 'Umrah Manasik Attendance'
    _order = 'manasik_id, pilgrim_id'
    _rec_name = 'pilgrim_id'

    manasik_id = fields.Many2one(
        'umrah.manasik', string='Manasik Session', required=True,
        index=True, ondelete='cascade')
    pilgrim_id = fields.Many2one(
        'umrah.pilgrim', string='Pilgrim', required=True, index=True,
        ondelete='cascade')
    attendance = fields.Selection(
        selection=ATTENDANCE_STATES, string='Attendance',
        default='absent', required=True)
    note = fields.Char()
    company_id = fields.Many2one(
        related='manasik_id.company_id', store=True, index=True, readonly=True)

    _pilgrim_uniq = models.Constraint(
        'UNIQUE (manasik_id, pilgrim_id)',
        'This pilgrim already has an attendance line on this manasik session.')
