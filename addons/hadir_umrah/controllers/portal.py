import base64

from odoo import http
from odoo.http import request


class UmrahPortalController(http.Controller):

    def _get_portal_pilgrim(self):
        """The pilgrim record of the current portal user.

        Relies on the portal record rules: only the pilgrim linked to the
        user's own partner is visible.
        """
        return request.env['umrah.pilgrim'].search([
            ('partner_id', '=', request.env.user.partner_id.id),
        ], limit=1)

    def _get_booking(self, booking_id, pilgrim):
        booking = request.env['umrah.booking'].search([('id', '=', booking_id)])
        if not booking or pilgrim not in booking.pilgrim_ids:
            return request.env['umrah.booking']
        return booking

    @http.route('/my/umrah', type='http', auth='user', website=True)
    def portal_my_umrah(self, **kwargs):
        pilgrim = self._get_portal_pilgrim()
        if not pilgrim:
            return request.redirect('/my')
        bookings = request.env['umrah.booking'].search(
            [('pilgrim_ids', 'in', pilgrim.ids)])
        if len(bookings) == 1:
            return request.redirect('/my/umrah/%d' % bookings.id)
        return request.render('hadir_umrah.portal_my_umrah', {
            'page_name': 'umrah',
            'pilgrim': pilgrim,
            'bookings': bookings,
        })

    @http.route('/my/umrah/<int:booking_id>', type='http', auth='user', website=True)
    def portal_umrah_booking(self, booking_id, uploaded=None, error=None, **kwargs):
        pilgrim = self._get_portal_pilgrim()
        if not pilgrim:
            return request.redirect('/my')
        booking = self._get_booking(booking_id, pilgrim)
        if not booking:
            return request.redirect('/my/umrah')
        attachments = pilgrim.document_ids.attachment_ids
        attachment_tokens = dict(zip(
            attachments.ids,
            attachments.sudo().generate_access_token(),
        )) if attachments else {}
        return request.render('hadir_umrah.portal_umrah_booking', {
            'page_name': 'umrah',
            'pilgrim': pilgrim,
            'booking': booking,
            'documents': pilgrim.document_ids,
            'manasiks': booking.manasik_ids,
            'flights': booking.flight_ids,
            'my_attendance': {
                att.manasik_id.id: att for att in pilgrim.attendance_ids},
            'attachment_tokens': attachment_tokens,
            'uploaded': uploaded,
            'error': error,
        })

    @http.route(
        '/my/umrah/document/<int:document_id>/upload',
        type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_document_upload(self, document_id, **post):
        pilgrim = self._get_portal_pilgrim()
        document = request.env['umrah.document'].search([('id', '=', document_id)])
        # Ownership is checked with the plain environment (record rules apply);
        # sudo() is only used afterwards to perform the write the portal group
        # is intentionally not allowed to do through RPC.
        if not pilgrim or not document or document.pilgrim_id != pilgrim:
            return request.redirect('/my/umrah')
        url = '/my/umrah/%d' % document.booking_id.id
        upload_file = request.httprequest.files.get('document_file')
        if not upload_file or not upload_file.filename:
            return request.redirect('%s?error=nofile' % url)
        if document.state not in ('missing', 'rejected', 'submitted', 'verification'):
            return request.redirect('%s?error=state' % url)
        attachment = request.env['ir.attachment'].sudo().create({
            'name': upload_file.filename,
            'datas': base64.b64encode(upload_file.read()),
            'res_model': document._name,
            'res_id': document.id,
            'mimetype': upload_file.mimetype,
        })
        document.sudo().write({
            'attachment_ids': [(4, attachment.id)],
            'reject_reason': False,
        })
        if document.sudo().state in ('missing', 'rejected'):
            document.sudo().action_submit()
        return request.redirect('%s?uploaded=%d' % (url, document.id))
