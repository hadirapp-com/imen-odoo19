from .common import IntercompanyCommon


class TestCreditNote(IntercompanyCommon):
    """T12: Credit note -> vendor bill refund with full traceability."""

    def test_12_credit_note_creates_refund_draft(self):
        bridge, so, invoice, link = self._full_chain()
        original_bill = link.target_move_id.sudo()
        self.assertEqual(original_bill.state, 'draft')

        wizard = self.env['account.move.reversal'].sudo().with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'journal_id': invoice.journal_id.id,
            'reason': 'Intercompany correction',
        })
        result = wizard.reverse_moves()
        credit_note = self.env['account.move'].sudo().browse(result['res_id'])
        self.assertEqual(credit_note.move_type, 'out_credit_note')

        credit_note.sudo().action_post()

        refund_link = credit_note.intercompany_move_link_id
        self.assertTrue(refund_link)
        self.assertEqual(refund_link.link_type, 'credit_note')
        self.assertNotEqual(refund_link, link)

        refund_bill = refund_link.target_move_id.sudo()
        self.assertTrue(refund_bill)
        self.assertEqual(refund_bill.move_type, 'in_refund')
        self.assertEqual(refund_bill.state, 'draft')
        self.assertEqual(refund_bill.company_id, self.company_a)
        self.assertEqual(refund_bill.reversed_entry_id, original_bill)
        self.assertEqual(refund_bill.amount_total, 1110.0)

        # original bill untouched: accounting history stays intact
        self.assertEqual(original_bill.state, 'draft')
        self.assertTrue(original_bill.id)
        self.assertEqual(bridge.log_ids.filtered(
            lambda l: l.operation == 'create_bill' and l.result == 'success').__len__(), 2)
