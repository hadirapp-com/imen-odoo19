from odoo import fields, models


class IntercompanySyncLog(models.Model):
    _name = 'intercompany.sync.log'
    _description = 'Intercompany Sync Log'
    _order = 'date desc, id desc'

    # Structured audit trail. Written only by the sync engine (via sudo, so
    # logging can never fail on ACL and can never be forged or edited through
    # the UI); users of the involved companies get read-only access.

    transaction_id = fields.Many2one(
        'intercompany.transaction', ondelete='set null', index=True)
    move_link_id = fields.Many2one('intercompany.move.link', ondelete='set null', index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)

    source_company_id = fields.Many2one('res.company', index=True)
    target_company_id = fields.Many2one('res.company', index=True)

    document_type = fields.Selection([
        ('rfq', 'Purchase RFQ'),
        ('quotation', 'Sales Quotation'),
        ('sale_order', 'Sales Order'),
        ('invoice', 'Customer Invoice'),
        ('credit_note', 'Credit Note'),
        ('vendor_bill', 'Vendor Bill'),
        ('refund', 'Vendor Refund'),
        ('payment_status', 'Payment Status'),
    ])
    source_doc_ref = fields.Char(string='Source Document')
    target_doc_ref = fields.Char(string='Target Document')

    operation = fields.Selection([
        ('create_transaction', 'Create Bridge'),
        ('create_quotation', 'Create Quotation'),
        ('revise_quotation', 'Revise Quotation'),
        ('confirm_so', 'Confirm Sales Order'),
        ('create_bill', 'Create Vendor Bill'),
        ('create_refund', 'Create Vendor Refund'),
        ('sync_payment', 'Sync Payment Status'),
        ('cancel', 'Cancel'),
        ('retry', 'Retry'),
    ])
    result = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('info', 'Info'),
    ], required=True, default='success')
    error_message = fields.Text()
    duration_ms = fields.Integer(string='Duration (ms)')
    retry_count = fields.Integer()
