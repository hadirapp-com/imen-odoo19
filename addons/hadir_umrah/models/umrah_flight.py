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
