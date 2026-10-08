from .common import IntercompanyCommon


class TestIdempotency(IntercompanyCommon):
    """T5: duplicate synchronization. T17: concurrent synchronization.
    T18: integration key uniqueness at DB level."""

    def test_05_double_send_creates_single_quotation(self):
        po = self._create_po()
        po.action_send_intercompany()
        first_so = po.intercompany_transaction_id.target_so_id.sudo()

        po.action_send_intercompany()  # second click / double submission
        quotations = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', po.name)])
        self.assertEqual(len(quotations), 1)
        self.assertEqual(quotations, first_so)

    def test_17_double_post_hook_single_bill(self):
        bridge, so, invoice, link = self._full_chain()
        bills = self.env['account.move'].sudo().search([
            ('move_type', '=', 'in_invoice'),
            ('partner_id', '=', self.partner_b.id),
            ('ref', '=', invoice.name),
        ])
        self.assertEqual(len(bills), 1)
        # simulate cron retry racing with a manual retry while link exists
        invoice.sudo()._intercompany_process_posted()
        self.assertEqual(len(link.transaction_id.move_link_ids), 1)
        self.assertEqual(len(bills), 1)
        self.assertEqual(link.target_move_id.sudo(), bills[0])

    def test_18_integration_key_db_uniqueness(self):
        po = self._create_po()
        bridge = self._send(po)
        self.assertTrue(bridge.integration_key)
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env['intercompany.transaction'].sudo().create({
                    'route_id': self.route.id,
                    'source_company_id': self.company_a.id,
                    'target_company_id': self.company_b.id,
                    'source_po_id': po.id,
                })
        duplicates = self.env['intercompany.transaction'].sudo().search_count([
            ('source_po_id', '=', po.id)])
        self.assertEqual(duplicates, 1)

        # move link uniqueness (concurrent hook + cron race)
        so = self._confirm(bridge)
        invoice = self._create_and_post_invoice(so)
        link = invoice.intercompany_move_link_id
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env['intercompany.move.link'].sudo().create({
                    'transaction_id': bridge.id,
                    'source_move_id': invoice.id,
                })
        self.assertEqual(self.env['intercompany.move.link'].sudo().search_count([
            ('source_move_id', '=', invoice.id)]), 1)
