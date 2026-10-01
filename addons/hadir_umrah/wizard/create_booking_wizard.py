from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..models.umrah_pilgrim import GENDERS


class UmrahBookingCreateWizard(models.TransientModel):
    _name = 'umrah.booking.create.wizard'
    _description = 'Create Umrah Booking Wizard'

    sale_order_id = fields.Many2one(
        'sale.order', string='Sales Order', required=True,
        domain=[('state', 'in', ('sale', 'done'))])
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    product_id = fields.Many2one(
        'product.template', string='Umrah Package', required=True,
        domain=[('is_umrah_package', '=', True)])
    departure_date = fields.Date(required=True)
    return_date = fields.Date(required=True)
    create_project = fields.Boolean(string='Create Project', default=True)
    pilgrim_ids = fields.One2many(
        'umrah.booking.create.wizard.line', 'wizard_id', string='Pilgrims')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env['sale.order'].browse(res.get('sale_order_id'))
        if not order.exists():
            return res
        res.setdefault('partner_id', order.partner_id.id)
        package_lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_id.is_umrah_package)
        if package_lines and 'product_id' in fields_list:
            res['product_id'] = package_lines[0].product_id.product_tmpl_id.id
        if 'pilgrim_ids' in fields_list and not res.get('pilgrim_ids'):
            quantity = max(int(sum(package_lines.mapped('product_uom_qty'))), 1)
            first = {
                'full_name': order.partner_id.name,
                'phone': order.partner_id.phone,
                'email': order.partner_id.email,
                'gender': 'male',
            }
            res['pilgrim_ids'] = [(0, 0, first)] + [
                (0, 0, {'gender': 'male'}) for _ in range(quantity - 1)]
        return res

    @api.constrains('departure_date', 'return_date')
    def _check_dates(self):
        for wizard in self:
            if (wizard.departure_date and wizard.return_date
                    and wizard.return_date <= wizard.departure_date):
                raise ValidationError(_('Return date must be after the departure date.'))

    def action_create_booking(self):
        self.ensure_one()
        order = self.sale_order_id
        if order.state not in ('sale', 'done'):
            raise UserError(_('The sales order must be confirmed before creating a booking.'))
        pilgrim_lines = self.pilgrim_ids.filtered(lambda l: l.full_name)
        if not pilgrim_lines:
            raise UserError(_('Add at least one pilgrim with a full name.'))
        booking = self.env['umrah.booking'].create({
            'partner_id': self.partner_id.id,
            'sale_order_id': order.id,
            'product_id': self.product_id.id,
            'departure_date': self.departure_date,
            'return_date': self.return_date,
            'user_id': order.user_id.id or self.env.uid,
            'company_id': order.company_id.id,
        })
        self.env['umrah.pilgrim'].create([{
            'booking_id': booking.id,
            'partner_id': line.partner_id.id,
            'full_name': line.full_name,
            'gender': line.gender,
            'birth_date': line.birth_date,
            'nik': line.nik,
            'phone': line.phone,
            'email': line.email,
            'passport_number': line.passport_number,
            'passport_expiry_date': line.passport_expiry_date,
        } for line in pilgrim_lines])
        booking._generate_document_checklist()
        if self.create_project:
            booking.action_create_project()
        order.message_post(body=_('Umrah booking %s created.', booking.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Umrah Booking'),
            'res_model': 'umrah.booking',
            'view_mode': 'form',
            'res_id': booking.id,
            'target': 'current',
        }


class UmrahBookingCreateWizardLine(models.TransientModel):
    _name = 'umrah.booking.create.wizard.line'
    _description = 'Umrah Booking Wizard Pilgrim Line'

    wizard_id = fields.Many2one(
        'umrah.booking.create.wizard', required=True, index=True, ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Contact',
        help='Leave empty to create a new contact automatically.')
    full_name = fields.Char(string='Full Name', required=True)
    gender = fields.Selection(selection=GENDERS, required=True, default='male')
    birth_date = fields.Date(string='Date of Birth')
    nik = fields.Char(string='NIK (National ID)')
    phone = fields.Char()
    email = fields.Char()
    passport_number = fields.Char(string='Passport Number')
    passport_expiry_date = fields.Date(string='Passport Expiry Date')
