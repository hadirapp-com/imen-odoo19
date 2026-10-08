from odoo import Command
from odoo.exceptions import UserError, ValidationError

from .common import IntercompanyCommon


class TestMappingErrors(IntercompanyCommon):
    """T6: product mapping missing. T7: partner not shareable.
    T8: tax mapping missing -> no invalid bill, error + retry available."""

    def test_06_missing_product_mapping_blocks_send(self):
        product_a = self.env['product.product'].create({
            'name': 'Buyer Only Product',
            'company_id': self.company_a.id,
            'type': 'service',
            'default_code': 'BUYER-ONLY',
        })
        po = self._create_po(product=product_a)
        self.route.product_mapping_required = True
        with self.assertRaises(UserError, msg='per-company product without mapping must fail'):
            po.action_send_intercompany()
        self.assertFalse(self.env['intercompany.transaction'].sudo().search_count([
            ('source_po_id', '=', po.id)]))
        self.assertFalse(self.env['sale.order'].sudo().search_count([
            ('client_order_ref', '=', po.name)]))

    def test_06b_default_code_automatic_match(self):
        self.env['product.product'].create({
            'name': 'Seller Twin Product',
            'company_id': self.company_b.id,
            'type': 'service',
            'default_code': 'TWIN-CODE',
        })
        product_a = self.env['product.product'].create({
            'name': 'Buyer Twin Product',
            'company_id': self.company_a.id,
            'type': 'service',
            'default_code': 'TWIN-CODE',
        })
        self.route.product_mapping_required = False
        po = self._create_po(product=product_a)
        po.action_send_intercompany()
        so = po.intercompany_transaction_id.target_so_id.sudo()
        self.assertEqual(so.order_line[0].product_id.default_code, 'TWIN-CODE')
        self.assertEqual(so.order_line[0].product_id.company_id, self.company_b)

    def test_07_partner_must_be_shared_across_companies(self):
        company_c = self.env['res.company'].create({'name': 'Other Co'})
        company_c.partner_id.write({'company_id': company_c})
        with self.assertRaises(ValidationError):
            self.env['intercompany.route'].create({
                'name': 'Bad Partner Route',
                'source_company_id': company_c.id,
                'target_company_id': self.company_b.id,
                'purchase_to_sale_enabled': True,
                'target_user_id': self.user_int_b.id,
            })

    def test_08_missing_tax_mapping_errors_and_retries(self):
        mapping = self.env['intercompany.tax.mapping'].sudo().search([
            ('route_id', '=', self.route.id),
            ('direction', '=', 'invoice_to_bill'),
        ])
        mapping.active = False

        bridge, so, invoice, link = self._full_chain()
        self.assertEqual(link.state, 'error')
        self.assertFalse(link.target_move_id)
        self.assertIn('unmapped tax', link.sync_error)
        self.assertEqual(link.retry_count, 1)
        # no invalid vendor bill was ever created on the buyer side
        self.assertFalse(self.env['account.move'].sudo().search_count([
            ('move_type', '=', 'in_invoice'),
            ('ref', '=', invoice.name),
        ]))
        self.assertTrue(bridge.log_ids.filtered(
            lambda l: l.operation == 'create_bill' and l.result == 'failed'))

        # fix the mapping, then retry - no duplicate, correct bill
        mapping.active = True
        link.action_retry()
        bill = link.target_move_id.sudo()
        self.assertTrue(bill)
        self.assertEqual(link.state, 'draft')
        self.assertEqual(bill.invoice_line_ids[0].tax_ids, self.tax_purchase_a)
