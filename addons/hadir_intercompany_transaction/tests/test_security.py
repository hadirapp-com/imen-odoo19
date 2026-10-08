from odoo.exceptions import AccessError

from .common import IntercompanyCommon


class TestSecurity(IntercompanyCommon):
    """T10: groups. T11: company A user cannot read company B documents,
    but keeps full access to the bridge."""

    def test_10_user_group_cannot_configure_routes(self):
        Route = self.env['intercompany.route'].with_user(self.user_a).with_context(
            allowed_company_ids=[self.company_a.id])
        with self.assertRaises(AccessError):
            Route.search_count([])
        with self.assertRaises(AccessError):
            Route.create({
                'name': 'Hacked Route',
                'source_company_id': self.company_a.id,
                'target_company_id': self.company_b.id,
            })
        # manager configures fine
        manager_route = self.env['intercompany.route'].with_user(self.user_manager).search([
            ('id', '=', self.route.id)])
        self.assertEqual(manager_route, self.route)

    def test_10b_logs_are_read_only_even_for_managers(self):
        Log = self.env['intercompany.sync.log'].with_user(self.user_manager).with_context(
            allowed_company_ids=[self.company_a.id, self.company_b.id])
        with self.assertRaises(AccessError):
            Log.create({'result': 'success'})

    def test_11_buyer_user_cannot_read_seller_documents(self):
        bridge = self._send(self._create_po())
        so = bridge.target_so_id.sudo()
        buyer_view = so.with_user(self.user_a).with_context(
            allowed_company_ids=[self.company_a.id])
        with self.assertRaises(AccessError):
            buyer_view.name  # noqa: B018 - access is the point
        with self.assertRaises(AccessError):
            buyer_view.read(['name'])

        # ... but the bridge itself is readable and shows the snapshots
        bridge_view = bridge.with_user(self.user_a).with_context(
            allowed_company_ids=[self.company_a.id])
        self.assertTrue(bridge_view.name.startswith('ICT/'))
        self.assertTrue(bridge_view.target_reference)
        self.assertTrue(bridge_view.line_ids)
        # and the buyer can still read his own RFQ side documents
        self.assertTrue(bridge_view.can_open_source_documents)
        self.assertFalse(bridge_view.can_open_target_documents)
