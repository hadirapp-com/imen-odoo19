from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

FLIGHT_TYPES = [
    ('outbound', 'Outbound (Departure)'),
    ('return', 'Return (Coming Back)'),
]


class UmrahFlight(models.Model):
    _name = 'umrah.flight'
    _description = 'Umrah Flight'
    _order = 'booking_id, sequence, departure_datetime'
    _rec_name = 'display_name'

    booking_id = fields.Many2one(
        'umrah.booking', string='Booking', required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    pilgrim_ids = fields.Many2many(
        'umrah.pilgrim', 'umrah_flight_pilgrim_rel', 'flight_id', 'pilgrim_id',
        string='Pilgrims',
        help='Passengers on this flight. New flights default to all pilgrims '
             'of the booking.')
    pilgrim_count = fields.Integer(compute='_compute_pilgrim_count')
    flight_type = fields.Selection(
        selection=FLIGHT_TYPES, string='Type', required=True, default='outbound')
    airline = fields.Char(required=True)
    flight_number = fields.Char(required=True)
    departure_city = fields.Char(string='Departure City')
    departure_airport = fields.Char(string='Departure Airport')
    departure_datetime = fields.Datetime(string='Departure Time')
    arrival_city = fields.Char(string='Arrival City')
    arrival_airport = fields.Char(string='Arrival Airport')
    arrival_datetime = fields.Datetime(string='Arrival Time')
    notes = fields.Text()
    company_id = fields.Many2one(
        related='booking_id.company_id', store=True, index=True, readonly=True)

    display_name = fields.Char(compute='_compute_display_name')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        booking_id = res.get('booking_id')
        if isinstance(booking_id, int) and 'pilgrim_ids' in fields_list \
                and not res.get('pilgrim_ids'):
            res['pilgrim_ids'] = [(6, 0, self.env['umrah.booking']
                                   .browse(booking_id).pilgrim_ids.ids)]
        return res

    @api.onchange('booking_id')
    def _onchange_booking_id(self):
        if self.booking_id and not self.pilgrim_ids:
            self.pilgrim_ids = self.booking_id.pilgrim_ids

    @api.depends('pilgrim_ids')
    def _compute_pilgrim_count(self):
        for flight in self:
            flight.pilgrim_count = len(flight.pilgrim_ids)

    @api.constrains('booking_id', 'pilgrim_ids')
    def _check_pilgrims_belong_to_booking(self):
        for flight in self:
            wrong = flight.pilgrim_ids.filtered(
                lambda p: p.booking_id != flight.booking_id)
            if wrong:
                raise ValidationError(_(
                    'Pilgrim(s) %(names)s do not belong to booking %(booking)s.',
                    names=', '.join(wrong.mapped('full_name')[:5]),
                    booking=flight.booking_id.name))

    @api.depends('airline', 'flight_number', 'departure_datetime')
    def _compute_display_name(self):
        for flight in self:
            parts = [flight.airline, flight.flight_number]
            if flight.departure_datetime:
                parts.append(fields.Datetime.context_timestamp(
                    flight, flight.departure_datetime).strftime('%d %b %Y'))
            flight.display_name = ' - '.join(p for p in parts if p)

    @api.constrains('departure_datetime', 'arrival_datetime')
    def _check_dates(self):
        for flight in self:
            if (flight.departure_datetime and flight.arrival_datetime
                    and flight.arrival_datetime < flight.departure_datetime):
                raise ValidationError(
                    _('Arrival time must be after the departure time.'))
