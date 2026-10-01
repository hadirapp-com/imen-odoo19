import logging
import re
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

NOTIFICATION_EVENTS = [
    ('document_reminder', 'Document Reminder'),
    ('payment_reminder', 'Payment Reminder'),
    ('manasik_reminder', 'Manasik Reminder'),
    ('visa_update', 'Visa Update'),
    ('departure_h7', 'H-7 Departure'),
    ('departure_h1', 'H-1 Departure'),
    ('custom', 'Custom'),
]

NOTIFICATION_STATES = [
    ('queued', 'Queued'),
    ('sent', 'Sent'),
    ('failed', 'Failed'),
    ('cancelled', 'Cancelled'),
]

_PHONE_RE = re.compile(r'[^\d]')


class UmrahNotificationTemplate(models.Model):
    _name = 'umrah.notification.template'
    _description = 'Umrah Notification Template'
    _inherit = ['mail.render.mixin']
    _order = 'event_type, id'

    name = fields.Char(required=True, translate=True)
    event_type = fields.Selection(
        selection=NOTIFICATION_EVENTS, required=True, index=True)
    body = fields.Text(
        string='Message Body', required=True,
        help='WhatsApp message. Use mail.template placeholders like '
             '${object.full_name} or ${object.booking_id.name}. The "object" is '
             'the pilgrim (document/H-7/H-1 reminders), the booking (payment '
             'reminder), the manasik session (manasik reminder) or the visa '
             '(visa update).')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company')

    _company_event_uniq = models.Constraint(
        'UNIQUE (event_type, company_id)',
        'Only one template per event type per company is allowed.')

    @api.constrains('event_type', 'company_id')
    def _check_single_template_per_event(self):
        for template in self:
            domain = [
                ('event_type', '=', template.event_type),
                ('id', '!=', template.id),
            ]
            if template.company_id:
                domain += ['|', ('company_id', '=', False),
                           ('company_id', '=', template.company_id.id)]
            if self.search_count(domain):
                raise ValidationError(_(
                    'Only one template per event type per company is allowed.'))


class UmrahNotification(models.Model):
    _name = 'umrah.notification'
    _description = 'Umrah Notification'
    _order = 'create_date desc, id desc'

    name = fields.Char(compute='_compute_name')
    event_type = fields.Selection(
        selection=NOTIFICATION_EVENTS, required=True, index=True)
    template_id = fields.Many2one(
        'umrah.notification.template', string='Template', required=True,
        ondelete='restrict')
    booking_id = fields.Many2one(
        'umrah.booking', string='Booking', required=True, index=True, ondelete='cascade')
    pilgrim_id = fields.Many2one(
        'umrah.pilgrim', string='Pilgrim', index=True, ondelete='set null')
    manasik_id = fields.Many2one(
        'umrah.manasik', string='Manasik Session', index=True, ondelete='set null')
    visa_id = fields.Many2one(
        'umrah.visa', string='Visa', index=True, ondelete='set null')
    partner_id = fields.Many2one(
        'res.partner', string='Recipient', required=True)
    phone = fields.Char(
        string='Phone (WhatsApp)',
        help='Recipient number in international format without + (e.g. '
             '628111002000). Editable before sending.')
    body = fields.Text(string='Message', readonly=True)
    state = fields.Selection(
        selection=NOTIFICATION_STATES, string='Status',
        default='queued', required=True, index=True)
    provider = fields.Char(readonly=True)
    provider_message_id = fields.Char(string='Provider Reference', readonly=True)
    error_message = fields.Text(string='Error', readonly=True)
    sent_date = fields.Datetime(readonly=True)
    company_id = fields.Many2one(
        related='booking_id.company_id', store=True, index=True, readonly=True)

    @api.depends('event_type', 'booking_id.name', 'partner_id.name')
    def _compute_name(self):
        labels = dict(NOTIFICATION_EVENTS)
        for notification in self:
            notification.name = '%s - %s (%s)' % (
                labels.get(notification.event_type, notification.event_type),
                notification.booking_id.name or '',
                notification.partner_id.name or '')

    # -----------------------------------------------------------------
    # Queue generation
    # -----------------------------------------------------------------
    @api.model
    def _normalize_phone_number(self, number):
        if not number:
            return False
        digits = _PHONE_RE.sub('', number)
        if digits.startswith('0'):
            digits = '62' + digits[1:]
        return digits or False

    @api.model
    def _queue_event(self, event_type, booking, pilgrims=None, manasik=None,
                     visa=None, dedup_days=3):
        """Queue one notification per recipient for an event.

        Recipients: pilgrims (or every pilgrim of the booking when pilgrims is
        None) for pilgrim events, the booking customer for the payment
        reminder. Skips recipients already notified for the same event within
        the deduplication window.
        """
        template = self.env['umrah.notification.template'].search([
            ('event_type', '=', event_type),
            '|', ('company_id', '=', False),
            ('company_id', '=', booking.company_id.id),
        ], limit=1)
        if not template:
            _logger.info(
                'hadir_umrah: no notification template for event %s, skipped.',
                event_type)
            return self.env['umrah.notification']

        if event_type == 'payment_reminder':
            recipients = [(booking.partner_id, None)]
        else:
            targets = booking.pilgrim_ids if pilgrims is None else pilgrims
            recipients = [(pilgrim.partner_id, pilgrim) for pilgrim in targets]

        vals_list = []
        for partner, pilgrim in recipients:
            phone = self._normalize_phone_number(
                (pilgrim.phone if pilgrim else False)
                or partner.phone or partner.mobile)
            if not phone:
                continue
            if self._recently_notified(event_type, phone, booking, dedup_days):
                continue
            render_model, render_res_id = self._get_render_target(
                event_type, booking, pilgrim, manasik, visa)
            try:
                body = template._render_template(
                    template.body, render_model, [render_res_id]).get(render_res_id)
            except Exception:
                # A broken template must never block the operational crons.
                _logger.exception(
                    'hadir_umrah: failed to render notification template %s.',
                    template.name)
                continue
            vals_list.append({
                'event_type': event_type,
                'template_id': template.id,
                'booking_id': booking.id,
                'pilgrim_id': pilgrim.id if pilgrim else False,
                'manasik_id': manasik.id if manasik else False,
                'visa_id': visa.id if visa else False,
                'partner_id': partner.id,
                'phone': phone,
                'body': body,
                'state': 'queued',
            })
        return self.create(vals_list)

    @api.model
    def _recently_notified(self, event_type, phone, booking, dedup_days):
        if not dedup_days:
            return False
        limit_date = fields.Datetime.now() - timedelta(days=dedup_days)
        return bool(self.search_count([
            ('event_type', '=', event_type),
            ('phone', '=', phone),
            ('booking_id', '=', booking.id),
            ('state', 'in', ('queued', 'sent')),
            ('create_date', '>=', limit_date),
        ]))

    @api.model
    def _get_render_target(self, event_type, booking, pilgrim, manasik, visa):
        if event_type == 'payment_reminder':
            return booking._name, booking.id
        if event_type == 'manasik_reminder':
            return manasik._name, manasik.id
        if event_type == 'visa_update':
            return visa._name, visa.id
        return pilgrim._name, pilgrim.id

    def action_queue_now(self):
        """Manual re-queue for cancelled/failed records (same content)."""
        self.filtered(lambda n: n.state in ('failed', 'cancelled')).write({
            'state': 'queued',
            'error_message': False,
        })
        return True

    def action_cancel(self):
        self.filtered(lambda n: n.state == 'queued').write({'state': 'cancelled'})
        return True

    # -----------------------------------------------------------------
    # Sending (provider abstraction)
    # -----------------------------------------------------------------
    def action_send(self):
        self.filtered(lambda n: n.state == 'queued')._process_sending()
        return True

    @api.model
    def _cron_send_notifications(self):
        queued = self.search(
            [('state', '=', 'queued')], limit=100, order='create_date asc')
        queued._process_sending()
        _logger.info('hadir_umrah: processed %s notification(s).', len(queued))

    def _process_sending(self):
        for notification in self:
            notification._process_single()

    def _process_single(self):
        self.ensure_one()
        if not self.phone:
            self.write({
                'state': 'failed',
                'error_message': _('Missing phone number.'),
            })
            return
        try:
            provider, provider_message_id = self._send_whatsapp()
        except Exception as error:
            self.write({
                'state': 'failed',
                'error_message': str(error),
            })
            return
        self.write({
            'state': 'sent',
            'provider': provider,
            'provider_message_id': provider_message_id,
            'sent_date': fields.Datetime.now(),
            'error_message': False,
        })

    def _send_whatsapp(self):
        """Send through the configured provider.

        Provider registry: 'log' marks the message as sent and logs the body
        (safe default for testing); 'http' posts a generic JSON payload to the
        configured API URL with the token in the Authorization header, which
        covers most WhatsApp gateway services. Custom provider modules should
        override _prepare_provider_payload() / _process_provider_response()
        or extend this method.
        """
        self.ensure_one()
        # sudo(): the API credentials live on the company and are restricted
        # to system administrators; the sending routine (cron or operator)
        # only needs to read them here.
        company = self.company_id.sudo()
        provider = company.umrah_whatsapp_provider or 'log'
        if provider == 'log':
            _logger.info(
                'hadir_umrah: WhatsApp (log provider) to %s for booking %s:\n%s',
                self.phone, self.booking_id.name, self.body)
            return 'log', False
        if provider == 'http':
            if not company.umrah_whatsapp_api_url:
                raise UserError(_(
                    'No WhatsApp API URL configured on the company settings.'))
            payload = self._prepare_provider_payload()
            response = requests.post(
                company.umrah_whatsapp_api_url,
                json=payload,
                headers={
                    'Authorization': company.umrah_whatsapp_api_token or '',
                    'Content-Type': 'application/json',
                },
                timeout=10,
            )
            return 'http', self._process_provider_response(response)
        raise UserError(_('Unknown WhatsApp provider "%s".', provider))

    def _prepare_provider_payload(self):
        """Extension point for custom provider modules."""
        self.ensure_one()
        return {'target': self.phone, 'message': self.body}

    def _process_provider_response(self, response):
        """Extension point for custom provider modules.

        Must return the provider message reference (or False).
        """
        if not 200 <= response.status_code < 300:
            raise UserError(_(
                'WhatsApp API error %(status)s: %(text)s',
                status=response.status_code, text=response.text[:200]))
        try:
            return response.json().get('id') or False
        except ValueError:
            return False

    # -----------------------------------------------------------------
    # Daily queue generation
    # -----------------------------------------------------------------
    @api.model
    def _cron_queue_notifications(self):
        """Daily: fill the sending queue from operational events."""
        today = fields.Date.context_today(self)
        Booking = self.env['umrah.booking']
        Pilgrim = self.env['umrah.pilgrim']
        Manasik = self.env['umrah.manasik']

        # Document reminders: pilgrims with incomplete documents, departure < 30 days
        pilgrims = Pilgrim.search([
            ('booking_id.state', 'in', ('document', 'verification')),
            ('booking_id.departure_date', '<=', fields.Date.add(today, days=30)),
            ('document_required_count', '>', 0),
        ]).filtered(lambda p: p.document_progress < 100.0)
        for booking in pilgrims.booking_id:
            affected = pilgrims.filtered(lambda p: p.booking_id == booking)
            self._queue_event(
                'document_reminder', booking, pilgrims=affected)

        # Payment reminders: overdue bookings
        for booking in Booking.search([
            ('payment_status', '=', 'overdue'),
            ('state', 'not in', ('cancelled', 'completed')),
        ]):
            self._queue_event('payment_reminder', booking)

        # Manasik reminders: sessions tomorrow
        for manasik in Manasik.search([('date', '=', fields.Date.add(today, days=1))]):
            self._queue_event(
                'manasik_reminder', manasik.booking_id, manasik=manasik)

        # Departure reminders H-7 and H-1
        for event, offset in (('departure_h7', 7), ('departure_h1', 1)):
            for booking in Booking.search([
                ('departure_date', '=', fields.Date.add(today, days=offset)),
                ('state', 'in', ('confirmed', 'document', 'verification', 'visa', 'ready')),
            ]):
                self._queue_event(event, booking)
