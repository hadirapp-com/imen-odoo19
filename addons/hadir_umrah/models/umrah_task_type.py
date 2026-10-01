from odoo import fields, models


class UmrahTaskType(models.Model):
    _name = 'umrah.task.type'
    _description = 'Umrah Task Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    anchor = fields.Selection(
        selection=[
            ('departure', 'Before Departure'),
            ('return', 'After Return'),
        ],
        string='Deadline Anchor', required=True, default='departure',
        help='The task deadline is computed from the booking departure date '
             '(H-offset) or from the return date (+offset).')
    deadline_offset = fields.Integer(
        string='Deadline Offset (days)', default=30,
        help='For "Before Departure": number of days before the departure date '
             '(H-60 = 60). For "After Return": number of days after the return date.')
    responsible_user_id = fields.Many2one(
        'res.users', string='Responsible', index=True,
        help='Default assignee of generated tasks. Falls back to the booking coordinator.')
    required = fields.Boolean(
        default=True,
        help='Required task types must be done before the booking can depart '
             '(enforced in a later phase).')
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company')

    _offset_check = models.Constraint(
        'CHECK (deadline_offset >= 0)',
        'The deadline offset cannot be negative.')


class ProjectTask(models.Model):
    _inherit = 'project.task'

    umrah_booking_id = fields.Many2one(
        'umrah.booking', string='Umrah Booking',
        index=True, copy=False, ondelete='cascade')
    task_type_id = fields.Many2one(
        'umrah.task.type', string='Task Type',
        index=True, copy=False,
        domain="[('company_id', 'in', [False, company_id])]")
    pilgrim_id = fields.Many2one(
        'umrah.pilgrim', string='Pilgrim',
        index=True,
        domain="[('booking_id', '=', umrah_booking_id)]",
        help='Optional: link this task to one specific pilgrim of the booking.')
