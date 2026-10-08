from .common import IntercompanyCommon


class TestFlowInvoiceBill(IntercompanyCommon):
    """T3: SO -> Customer Invoice (native). T4: Invoice -> Vendor Bill.
    T16: Payment status mirror (informational, no payment copying)."""

    def test_03_invoice_posted_keeps_native_flow(self):
        bridge, so, invoice, link = self._full_chain()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.company_id, self.company_b)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.amount_total, 1110.0)
        # buyer-side bill exists as draft, so the chain is not complete yet
        self.assertEqual(bridge.sync_state, 'partially_invoiced')

    def test_04_invoice_creates_draft_vendor_bill(self):
        bridge, so, invoice, link = self._full_chain()
        bill = link.target_move_id.sudo()
        self.assertTrue(bill)
        self.assertEqual(link.state, 'draft')
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.state, 'draft')
        self.assertEqual(bill.company_id, self.company_a)
        self.assertEqual(bill.partner_id, self.partner_b)
        self.assertEqual(bill.ref, invoice.name)
        self.assertEqual(bill.invoice_line_ids[0].tax_ids, self.tax_purchase_a)
        self.assertEqual(bill.amount_total, 1110.0)
        self.assertEqual(bill.amount_untaxed, 1000.0)

    def test_16_payment_status_mirror_no_payment_copy(self):
        bridge, so, invoice, link = self._full_chain()
        bill = link.target_move_id.sudo()
        self.assertEqual(bill.state, 'draft')

        wizard = self.env['account.payment.register'].sudo().with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'amount': invoice.amount_total})
        wizard._create_payments()
        self.assertIn(invoice.sudo().payment_state, ('paid', 'in_payment'))

        link.invalidate_recordset()
        self.assertIn(link.payment_state, ('paid', 'in_payment'))
        self.assertTrue(link.payment_reference)
        # no payment entry was created on the buyer side by the bridge:
        # the buyer bill is still unpaid until buyer accounting pays it
        self.assertEqual(bill.payment_state, 'not_paid')
        self.assertEqual(bridge.log_ids.filtered(
            lambda l: l.operation == 'sync_payment').__len__(), 1)
