from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    intercompany_transaction_id = fields.Many2one(
        'intercompany.transaction', string='Intercompany Transaction',
        copy=False, index=True, check_company=False,
        help='Bridge record of the intercompany flow. All cross-company '
             'information is readable there, even without multi-company access.')

    intercompany_sync_state = fields.Selection(
        related='intercompany_transaction_id.sync_state',
        string='Intercompany Status')

    def action_send_intercompany(self):
        """Create (once) the intercompany bridge for this RFQ and, if the route
        allows it, the native sales quotation in the seller company. Fully
        idempotent: unique(source_po_id) + re-entry guards."""
        for po in self:
            if po.intercompany_transaction_id:
                continue
            if po.state not in ('draft', 'sent'):
                raise UserError(_('Only a draft or sent RFQ can be sent to the intercompany bridge.'))
            route = self.env['intercompany.route']._find_for_purchase_order(po)
            if not route:
                raise UserError(_(
                    'No active intercompany route for vendor "%(vendor)s" in company '
                    '"%(company)s". Configure one in Intercompany > Configuration > Routes.',
                    vendor=po.partner_id.display_name, company=po.company_id.name))
            errors = self.env['intercompany.transaction']._collect_purchase_order_errors(po, route)
            if errors:
                raise UserError(_('Cannot send RFQ %s:\n%s', po.name, '\n'.join(errors)))
            Bridge = self.env['intercompany.transaction'].sudo()
            bridge = Bridge.create({
                'route_id': route.id,
                'source_company_id': po.company_id.id,
                'target_company_id': route.target_company_id.id,
                'source_po_id': po.id,
            })
            po.write({'intercompany_transaction_id': bridge.id})
            bridge._snapshot_purchase_order()
            bridge._log('create_transaction', document_type='rfq',
                        source_doc_ref=po.name)
            bridge.action_sync_now()
        return self._action_open_intercompany()

    def _action_open_intercompany(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Intercompany Transaction'),
            'res_model': 'intercompany.transaction',
            'res_id': self.intercompany_transaction_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_intercompany(self):
        return self._action_open_intercompany()
