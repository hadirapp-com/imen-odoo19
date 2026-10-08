from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class IntercompanyCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env

        cls.company_a = env['res.company'].create({'name': 'Buyer Co'})
        cls.company_b = env['res.company'].create({'name': 'Seller Co'})
        cls.partner_a = cls.company_a.partner_id
        cls.partner_b = cls.company_b.partner_id
        (cls.partner_a | cls.partner_b).write({'company_id': False})

        cls.product = env['product.product'].create({
            'name': 'Shared Widget',
            'company_id': False,
            'type': 'service',
            'invoice_policy': 'order',
            'list_price': 100.0,
            'standard_price': 50.0,
        })

        cls.tax_purchase_a = env['account.tax'].create({
            'name': 'PPN Masukan 11 (A)',
            'amount': 11,
            'type_tax_use': 'purchase',
            'company_id': cls.company_a.id,
        })
        cls.tax_sale_b = env['account.tax'].create({
            'name': 'PPN Keluaran 11 (B)',
            'amount': 11,
            'type_tax_use': 'sale',
            'company_id': cls.company_b.id,
        })

        cls.user_int_a = env['res.users'].create({
            'name': 'Integration Buyer',
            'login': 'ict-int-buyer',
            'email': 'ict-buyer@example.com',
            'company_id': cls.company_a.id,
            'company_ids': [Command.set(cls.company_a.ids)],
            'group_ids': [Command.set([
                env.ref('base.group_user').id,
                env.ref('account.group_invoice').id,
            ])],
        })
        cls.user_int_b = env['res.users'].create({
            'name': 'Integration Seller',
            'login': 'ict-int-seller',
            'email': 'ict-seller@example.com',
            'company_id': cls.company_b.id,
            'company_ids': [Command.set(cls.company_b.ids)],
            'group_ids': [Command.set([
                env.ref('base.group_user').id,
                env.ref('sales_team.group_sale_salesman').id,
                env.ref('account.group_invoice').id,
            ])],
        })
        cls.user_a = env['res.users'].create({
            'name': 'Buyer User',
            'login': 'ict-buyer-user',
            'email': 'buyer-user@example.com',
            'company_id': cls.company_a.id,
            'company_ids': [Command.set(cls.company_a.ids)],
            'group_ids': [Command.set([
                env.ref('base.group_user').id,
                env.ref('hadir_intercompany_transaction.group_intercompany_user').id,
            ])],
        })
        cls.user_manager = env['res.users'].create({
            'name': 'Intercompany Manager',
            'login': 'ict-manager',
            'email': 'ict-manager@example.com',
            'company_id': cls.company_a.id,
            'company_ids': [Command.set(cls.company_a.ids)],
            'group_ids': [Command.set([
                env.ref('base.group_user').id,
                env.ref('hadir_intercompany_transaction.group_intercompany_manager').id,
            ])],
        })

        cls.route = env['intercompany.route'].create({
            'name': 'Buyer Co - Seller Co',
            'source_company_id': cls.company_a.id,
            'target_company_id': cls.company_b.id,
            'purchase_to_sale_enabled': True,
            'auto_create_vendor_bill': True,
            'target_user_id': cls.user_int_b.id,
            'source_user_id': cls.user_int_a.id,
        })
        env['intercompany.tax.mapping'].create({
            'route_id': cls.route.id,
            'direction': 'rfq_to_quotation',
            'source_tax_id': cls.tax_purchase_a.id,
            'target_tax_id': cls.tax_sale_b.id,
        })
        env['intercompany.tax.mapping'].create({
            'route_id': cls.route.id,
            'direction': 'invoice_to_bill',
            'source_tax_id': cls.tax_sale_b.id,
            'target_tax_id': cls.tax_purchase_a.id,
        })

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _create_po(self, qty=10.0, price=100.0, product=None, taxes=True):
        return self.env['purchase.order'].with_company(self.company_a).create({
            'partner_id': self.partner_b.id,
            'order_line': [Command.create({
                'product_id': (product or self.product).id,
                'name': (product or self.product).display_name,
                'product_qty': qty,
                'price_unit': price,
                'taxes_id': [Command.set(
                    self.tax_purchase_a.ids if taxes else [])],
            })],
        })

    def _send(self, po):
        po.action_send_intercompany()
        return po.intercompany_transaction_id

    def _confirm(self, bridge):
        so = bridge.target_so_id.sudo()
        so.action_confirm()
        return so

    def _create_and_post_invoice(self, so):
        invoice = so.sudo()._create_invoices()
        invoice.sudo().write({'invoice_date': fields.Date.today()})
        invoice.sudo().action_post()
        return invoice

    def _full_chain(self):
        bridge = self._send(self._create_po())
        so = self._confirm(bridge)
        invoice = self._create_and_post_invoice(so)
        link = invoice.intercompany_move_link_id
        return bridge, so, invoice, link
