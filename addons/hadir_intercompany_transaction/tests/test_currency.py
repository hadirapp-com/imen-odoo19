from odoo import Command, fields

from .common import IntercompanyCommon


class TestCurrency(IntercompanyCommon):
    """T9: different company currencies - source currency is kept on the target
    documents (native multi-currency), conversion rate is recorded."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        usd = cls.env.ref('base.USD')
        eur = cls.env.ref('base.EUR')
        cls.company_b.currency_id = eur.id
        cls.env['res.currency.rate'].create({
            'currency_id': usd.id,
            'name': fields.Date.today(),
            'rate': 1.1,
            'company_id': cls.company_b.id,
        })

    def test_09_currency_kept_and_rate_recorded(self):
        po = self._create_po()
        po.action_send_intercompany()
        bridge = po.intercompany_transaction_id
        so = bridge.target_so_id.sudo()
        self.assertEqual(so.currency_id, po.currency_id)
        self.assertEqual(so.amount_total, 1110.0)
        self.assertTrue(self.env['res.currency.rate'].sudo().search_count([
            ('currency_id', '=', po.currency_id.id),
            ('company_id', '=', self.company_b.id)]))

        self._confirm(bridge)
        invoice = self._create_and_post_invoice(so)
        link = invoice.intercompany_move_link_id
        bill = link.target_move_id.sudo()
        self.assertEqual(bill.currency_id, invoice.currency_id)
        self.assertEqual(bill.amount_total, invoice.amount_total)
        self.assertEqual(link.exchange_rate, 1.0)
