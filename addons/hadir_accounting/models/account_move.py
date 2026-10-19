from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    hadir_asset_id = fields.Many2one(
        'account.asset', string='Asset', index=True, copy=False,
        ondelete='restrict', check_company=True,
        help="Depreciation entry generated for this asset/deferred entry.")

    def button_draft(self):
        linked = self.mapped('hadir_asset_id').filtered(lambda a: a.state in ('running', 'closed'))
        if linked:
            raise UserError(_(
                "You cannot reset depreciation entries of a running/closed asset. "
                "Set the asset back to draft first: %s.", ', '.join(linked.mapped('display_name'))))
        return super().button_draft()

    def button_cancel(self):
        linked = self.mapped('hadir_asset_id').filtered(lambda a: a.state in ('running', 'closed'))
        if linked:
            raise UserError(_(
                "You cannot cancel depreciation entries of a running/closed asset. "
                "Set the asset back to draft first: %s.", ', '.join(linked.mapped('display_name'))))
        return super().button_cancel()
