from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    umrah_booking_ids = fields.One2many(
        'umrah.booking', 'sale_order_id', string='Umrah Bookings')
    umrah_booking_count = fields.Integer(
        string='Booking Count',
        compute='_compute_umrah_booking_count')

    @api.depends('umrah_booking_ids')
    def _compute_umrah_booking_count(self):
        for order in self:
            order.umrah_booking_count = len(order.umrah_booking_ids)

    def action_view_umrah_bookings(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Umrah Bookings'),
            'res_model': 'umrah.booking',
            'view_mode': 'list,form,kanban',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_company_id': self.company_id.id,
            },
        }
        if self.umrah_booking_count == 1:
            action.update({
                'res_id': self.umrah_booking_ids[0].id,
                'view_mode': 'form',
            })
        return action

    def action_create_umrah_booking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Umrah Booking'),
            'res_model': 'umrah.booking.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }
