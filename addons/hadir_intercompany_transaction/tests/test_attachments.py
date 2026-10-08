import base64

from odoo import fields

from .common import IntercompanyCommon


class TestAttachments(IntercompanyCommon):
    """T15: attachment copy-on-sync; filestore dedup keeps storage flat."""

    def _attach(self, record, name='document.pdf'):
        return self.env['ir.attachment'].sudo().create({
            'name': name,
            'datas': base64.b64encode(b'%PDF-1.4 intercompany test'),
            'mimetype': 'application/pdf',
            'res_model': record._name,
            'res_id': record.id,
        })

    def test_15_rfq_attachment_copied_to_bridge(self):
        po = self._create_po()
        attachment = self._attach(po, 'rfq.pdf')
        bridge = self._send(po)
        bridge_attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'intercompany.transaction'),
            ('res_id', '=', bridge.id),
        ])
        self.assertEqual(bridge_attachments.mapped('name'), ['rfq.pdf'])
        self.assertEqual(
            bridge_attachments.checksum, attachment.checksum,
            'copy-on-sync must reuse the same filestore content (sha1)')

    def test_15b_invoice_attachment_copied_to_bill(self):
        bridge = self._send(self._create_po())
        so = self._confirm(bridge)
        invoice = so.sudo()._create_invoices()
        self._attach(invoice, 'invoice-detail.pdf')
        invoice.sudo().write({'invoice_date': fields.Date.today()})
        invoice.sudo().action_post()
        link = invoice.intercompany_move_link_id
        bill = link.target_move_id.sudo()
        bill_attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', bill.id),
        ])
        self.assertEqual(bill_attachments.mapped('name'), ['invoice-detail.pdf'])
