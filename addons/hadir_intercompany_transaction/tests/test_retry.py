from odoo.exceptions import UserError

from .common import IntercompanyCommon


class TestRetry(IntercompanyCommon):
    """T14: retry after synchronization error reuses the existing keys."""

    def test_14_retry_creates_missing_quotation(self):
        po = self._create_po()
        self.route.auto_create_quotation = False
        po.action_send_intercompany()
        bridge = po.intercompany_transaction_id
        self.assertEqual(bridge.sync_state, 'draft')
        self.assertFalse(bridge.target_so_id)

        self.route.auto_create_quotation = True
        bridge.action_sync_now()
        so = bridge.target_so_id.sudo()
        self.assertTrue(so)
        self.assertEqual(bridge.sync_state, 'quotation_created')
        self.assertEqual(bridge.retry_count, 0)

    def test_14b_retry_raises_meaningful_validation_error(self):
        po = self._create_po()
        self.route.auto_create_quotation = False
        po.action_send_intercompany()
        bridge = po.intercompany_transaction_id

        tax_mapping = self.env['intercompany.tax.mapping'].sudo().search([
            ('route_id', '=', self.route.id),
            ('direction', '=', 'rfq_to_quotation'),
        ])
        tax_mapping.active = False
        with self.assertRaises(UserError):
            bridge.action_sync_now()
        self.assertEqual(bridge.sync_state, 'draft')

        tax_mapping.active = True
        bridge.action_sync_now()
        self.assertTrue(bridge.target_so_id)

    def test_14c_cron_retries_errored_transactions(self):
        po = self._create_po()
        self.route.auto_create_quotation = False
        po.action_send_intercompany()
        bridge = po.intercompany_transaction_id
        bridge.sudo().write({'sync_state': 'error', 'sync_error': 'simulate failure'})

        tax_mapping = self.env['intercompany.tax.mapping'].sudo().search([
            ('route_id', '=', self.route.id),
            ('direction', '=', 'rfq_to_quotation'),
        ])
        tax_mapping.active = False
        self.env['intercompany.transaction']._cron_retry()
        self.assertEqual(bridge.retry_count, 1)
        self.assertFalse(bridge.target_so_id)

        tax_mapping.active = True
        self.env['intercompany.transaction']._cron_retry()
        self.assertTrue(bridge.target_so_id)
        self.assertEqual(bridge.sync_state, 'quotation_created')
