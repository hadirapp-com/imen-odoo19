from .common import IntercompanyCommon


class TestCancellation(IntercompanyCommon):
    """T13: cancellations preserve audit history and behave per state."""

    def test_13a_cancel_quotation_before_confirm(self):
        bridge = self._send(self._create_po())
        bridge.target_so_id.sudo().action_cancel()
        self.assertEqual(bridge.sync_state, 'cancelled')
        # bridge is never deleted: history stays
        self.assertTrue(bridge.active)
        self.assertTrue(bridge.target_so_id)

    def test_13b_cancel_invoice_auto_cancels_draft_bill(self):
        bridge, so, invoice, link = self._full_chain()
        bill = link.target_move_id.sudo()
        self.assertEqual(bill.state, 'draft')
        invoice.sudo().button_cancel()
        self.assertEqual(bill.state, 'cancel')
        self.assertEqual(link.state, 'cancelled')
        self.assertTrue(bridge.log_ids.filtered(lambda l: l.operation == 'cancel'))
        # bill was cancelled, not deleted
        self.assertTrue(bill.exists())

    def test_13c_cancel_invoice_with_posted_bill_needs_credit_note(self):
        self.route.vendor_bill_auto_post = True
        bridge, so, invoice, link = self._full_chain()
        bill = link.target_move_id.sudo()
        self.assertEqual(bill.state, 'posted')
        invoice.sudo().button_cancel()
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(link.state, 'error')
        self.assertIn('credit note', link.sync_error)
