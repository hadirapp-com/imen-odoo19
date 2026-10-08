from .common import IntercompanyCommon


class TestFlowRfqQuotation(IntercompanyCommon):
    """T1: RFQ -> Quotation. T2: Quotation -> Sales Order."""

    def test_01_send_rfq_creates_quotation(self):
        po = self._create_po()
        po.action_send_intercompany()
        bridge = po.intercompany_transaction_id
        self.assertTrue(bridge, 'bridge must be created')
        self.assertEqual(bridge.sync_state, 'quotation_created')
        self.assertTrue(bridge.name.startswith('ICT/'))
        self.assertEqual(bridge.integration_key, 'ICT-PO-%s' % po.id)

        so = bridge.target_so_id.sudo()
        self.assertTrue(so)
        self.assertEqual(so.state, 'draft')
        self.assertEqual(so.company_id, self.company_b)
        self.assertEqual(so.partner_id, self.partner_a)
        self.assertEqual(so.client_order_ref, po.name)

        line = so.order_line.filtered(lambda l: not l.display_type)[0]
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.product_uom_qty, 10.0)
        self.assertEqual(line.price_unit, 100.0)
        self.assertEqual(line.tax_id, self.tax_sale_b)
        self.assertEqual(so.amount_total, 1110.0)

        snapshot = bridge.line_ids[0]
        self.assertEqual(snapshot.source_product_name, self.product.display_name)
        self.assertEqual(snapshot.target_product_name, self.product.display_name)
        self.assertEqual(snapshot.target_subtotal, 1000.0)

        logs = bridge.log_ids
        self.assertTrue(logs.filtered(
            lambda l: l.operation == 'create_quotation' and l.result == 'success'))

    def test_02_confirm_quotation_updates_bridge(self):
        bridge = self._send(self._create_po())
        so = self._confirm(bridge)
        self.assertEqual(bridge.sync_state, 'so_confirmed')
        self.assertEqual(bridge.target_reference, so.name)
        self.assertTrue(bridge.log_ids.filtered(lambda l: l.operation == 'confirm_so'))
        # buyer RFQ sees the status through the bridge (snapshot, no cross-company read)
        self.assertEqual(bridge.sync_state, 'so_confirmed')
