import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

ASSET_LOCKED_FIELDS = [
    'original_value', 'salvage_value', 'acquisition_date',
    'depreciation_start_date', 'duration_months', 'method',
    'degressive_factor', 'journal_id', 'account_asset_id',
    'account_depreciation_id', 'asset_type', 'is_deferred', 'company_id',
]


class AccountAsset(models.Model):
    _name = 'account.asset'
    _description = 'Asset / Deferred Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'acquisition_date desc, id desc'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(tracking=True)
    asset_type = fields.Selection(
        [('purchase', 'Purchase (Expense)'),
         ('sale', 'Sale (Revenue)')],
        required=True, default='purchase', tracking=True,
        help="Purchase: the depreciation credits the asset account and debits "
             "the expense/amortization account. Sale (deferred revenue): the "
             "depreciation debits the asset account and credits the revenue account.")
    is_deferred = fields.Boolean(
        string='Deferred Entry', tracking=True,
        help="Deferred revenue/expense are amortized straight-line only, "
             "without salvage value.")
    state = fields.Selection(
        [('draft', 'Draft'), ('running', 'Running'), ('closed', 'Closed')],
        required=True, default='draft', tracking=True, copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    partner_id = fields.Many2one('res.partner', string='Partner',
                                 check_company=True, tracking=True)
    original_value = fields.Monetary(required=True, tracking=True)
    salvage_value = fields.Monetary(
        help="Residual value kept on the balance sheet at the end of the "
             "depreciation (ignored for deferred entries).")
    acquisition_date = fields.Date(required=True, tracking=True)
    depreciation_start_date = fields.Date(
        required=True,
        help="First day on which depreciation starts (prorata temporis "
             "applies on the first month).")
    duration_months = fields.Integer(required=True, default=60)
    method = fields.Selection(
        [('straight_line', 'Straight Line (linear)'),
         ('degressive', 'Degressive (declining)')],
        required=True, default='straight_line')
    degressive_factor = fields.Float(
        string='Degressive Factor (%)', default=100.0,
        help="Declining rate per year = factor / (100 x duration in years). "
             "E.g. 200 over 5 years = 40% of the net book value per year. "
             "Automatically switches to straight-line so the asset always "
             "ends at its salvage value.")
    journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True,
        domain="[('type', '=', 'general')]")
    account_asset_id = fields.Many2one(
        'account.account', string='Asset Account', required=True,
        check_company=True,
        help="Balance-sheet account holding the asset (or the deferral).")
    account_depreciation_id = fields.Many2one(
        'account.account', string='Depreciation/Amortization Account',
        required=True, check_company=True,
        help="P&L account for the expense (purchase) or revenue (sale) side.")
    depreciation_move_ids = fields.One2many(
        'account.move', 'hadir_asset_id', string='Depreciation Entries')
    depreciation_move_count = fields.Integer(compute='_compute_depreciation_counts')
    depreciation_value = fields.Monetary(
        string='Depreciated Amount', compute='_compute_book_values', store=True)
    book_value = fields.Monetary(
        compute='_compute_book_values', store=True,
        help="Original value minus posted depreciation entries.")
    next_depreciation_date = fields.Date(compute='_compute_next_depreciation')
    monthly_depreciation = fields.Monetary(
        compute='_compute_monthly_depreciation',
        help="Average monthly amount (straight-line view of the board).")
    depreciation_schedule = fields.Html(
        compute='_compute_depreciation_schedule', sanitize=False)

    @api.constrains('original_value', 'salvage_value', 'duration_months')
    def _check_values(self):
        for asset in self:
            if asset.salvage_value < 0 or asset.salvage_value >= asset.original_value:
                raise ValidationError(_("Salvage value must be positive and lower than the original value."))
            if asset.duration_months <= 0:
                raise ValidationError(_("The depreciation duration must be at least one month."))

    @api.constrains('is_deferred', 'method', 'salvage_value')
    def _check_deferred(self):
        for asset in self:
            if asset.is_deferred and asset.method != 'straight_line':
                raise ValidationError(_("Deferred entries must use the straight-line method."))
            if asset.is_deferred and asset.salvage_value:
                raise ValidationError(_("Deferred entries cannot have a salvage value."))

    @api.onchange('acquisition_date')
    def _onchange_acquisition_date(self):
        if self.acquisition_date and not self.depreciation_start_date:
            self.depreciation_start_date = self.acquisition_date

    @api.onchange('is_deferred')
    def _onchange_is_deferred(self):
        if self.is_deferred:
            self.method = 'straight_line'
            self.salvage_value = 0.0
            self.duration_months = 12

    def _compute_depreciation_counts(self):
        groups = self.env['account.move']._read_group(
            [('hadir_asset_id', 'in', self.ids)], ['hadir_asset_id'], ['__count'])
        counts = {asset.id: count for asset, count in groups}
        for asset in self:
            asset.depreciation_move_count = counts.get(asset.id, 0)

    @api.depends('depreciation_move_ids.state', 'depreciation_move_ids.amount_total_signed',
                 'original_value')
    def _compute_book_values(self):
        for asset in self:
            posted = asset.depreciation_move_ids.filtered(lambda m: m.state == 'posted')
            asset.depreciation_value = sum(posted.mapped('amount_total_signed'))
            asset.book_value = asset.original_value - asset.depreciation_value

    def _compute_next_depreciation(self):
        today = fields.Date.context_today(self)
        for asset in self:
            if asset.state != 'running':
                asset.next_depreciation_date = False
                continue
            posted_dates = set(asset.depreciation_move_ids.filtered(
                lambda m: m.state in ('posted', 'draft')).mapped('date'))
            board = asset._compute_depreciation_board()
            upcoming = [entry['date'] for entry in board
                        if entry['date'] <= today and entry['date'] not in posted_dates]
            asset.next_depreciation_date = min(upcoming) if upcoming else False

    def _compute_monthly_depreciation(self):
        for asset in self:
            depreciable = asset.original_value - (0.0 if asset.is_deferred else asset.salvage_value)
            asset.monthly_depreciation = depreciable / asset.duration_months

    # -----------------------------------------------------------------
    # Depreciation board
    # -----------------------------------------------------------------

    def _board_month_ends(self):
        self.ensure_one()
        start = self.depreciation_start_date
        month_end = self._month_end(start)
        ends = [month_end]
        for _i in range(self.duration_months - 1):
            first_next = month_end + timedelta(days=1)
            month_end = self._month_end(first_next)
            ends.append(month_end)
        return ends

    @staticmethod
    def _month_end(day):
        if day.month == 12:
            return date(day.year, 12, 31)
        return date(day.year, day.month + 1, 1) - timedelta(days=1)

    def _compute_depreciation_board(self):
        """Return [{'date': date, 'amount': float}] exactly totalling
        original_value - salvage_value, prorata temporis on the first month."""
        self.ensure_one()
        depreciable = self.original_value - self.salvage_value
        if depreciable <= 0 or self.duration_months <= 0:
            return []
        ends = self._board_month_ends()
        total_days = (ends[0] - self.depreciation_start_date).days + 1
        days_in_month = ends[0].day
        first_fraction = min(1.0, total_days / days_in_month)
        currency = self.currency_id

        amounts = []
        if self.method == 'straight_line':
            monthly = depreciable / self.duration_months
            for i in range(self.duration_months):
                if i == 0:
                    amounts.append(currency.round(monthly * first_fraction))
                elif i == self.duration_months - 1:
                    amounts.append(currency.round(depreciable - sum(amounts)))
                else:
                    amounts.append(currency.round(monthly))
        else:  # degressive, switches to linear
            years = self.duration_months / 12.0
            rate = (self.degressive_factor / 100.0) / years
            nbv = self.original_value
            months_left = self.duration_months
            for i in range(self.duration_months):
                deg = currency.round(nbv * rate / 12.0)
                lin = currency.round((nbv - self.salvage_value) / months_left)
                if lin >= deg or i == self.duration_months - 1:
                    amounts.append(lin)
                    nbv -= lin
                    months_left -= 1
                    # fill the remaining months linearly
                    remaining = nbv - self.salvage_value
                    per = currency.round(remaining / months_left) if months_left else 0.0
                    for j in range(i + 1, self.duration_months):
                        if j == self.duration_months - 1:
                            amounts.append(currency.round(nbv - self.salvage_value - per * (months_left - 1)))
                        else:
                            amounts.append(per)
                        nbv -= amounts[-1]
                        months_left -= 1
                    break
                amounts.append(deg if i else currency.round(deg * first_fraction))
                nbv -= amounts[-1]
                months_left -= 1

        board = [{'date': ends[i], 'amount': amounts[i]} for i in range(len(ends))]
        # exactness guard: force the total to the depreciable amount
        diff = currency.round(depreciable - sum(a['amount'] for a in board))
        if diff:
            board[-1]['amount'] = currency.round(board[-1]['amount'] + diff)
        return board

    def _compute_depreciation_schedule(self):
        for asset in self:
            asset.depreciation_schedule = asset._render_schedule_html()

    def _render_schedule_html(self):
        """Preview of the board for the form view."""
        self.ensure_one()
        posted_dates = set(self.depreciation_move_ids.filtered(
            lambda m: m.state in ('posted', 'draft')).mapped('date'))
        rows = []
        currency = self.currency_id or self.env.company.currency_id
        for entry in self._compute_depreciation_board():
            status = _('Posted') if entry['date'] in posted_dates else _('Upcoming')
            rows.append(
                '<tr><td>%s</td><td class="text-end">%s</td><td>%s</td></tr>' % (
                    entry['date'].strftime('%b %Y'),
                    '{:,.2f}'.format(entry['amount']),
                    status))
        return (
            '<table class="table table-sm"><thead><tr><th>%s</th><th class="text-end">%s</th>'
            '<th>%s</th></tr></thead><tbody>%s</tbody></table>'
            % (_('Date'), _('Amount'), _('Status'), ''.join(rows)))

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------

    def action_validate(self):
        for asset in self:
            if asset.state != 'draft':
                continue
            if not asset._compute_depreciation_board():
                raise UserError(_("The depreciation board is empty; check the value and duration."))
            if asset.is_deferred and not asset.partner_id:
                raise UserError(_("A deferred entry should reference the related customer/vendor."))
        self.write({'state': 'running'})

    def action_set_draft(self):
        for asset in self:
            if asset.depreciation_move_ids.filtered(lambda m: m.state == 'posted'):
                raise UserError(_("Reset posted depreciation entries first (reset the asset's moves)."))
            asset.depreciation_move_ids.filtered(
                lambda m: m.state == 'draft').unlink()
        self.write({'state': 'draft'})

    def action_view_depreciation_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Depreciation Entries'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('hadir_asset_id', '=', self.id)],
            'context': {'default_hadir_asset_id': self.id,
                        'default_move_type': 'entry',
                        'default_journal_id': self.journal_id.id},
        }

    def action_dispose(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dispose Asset'),
            'res_model': 'hadir.asset.dispose',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_asset_id': self.id},
        }

    # -----------------------------------------------------------------
    # Cron
    # -----------------------------------------------------------------

    @api.model
    def _cron_generate_entries(self):
        assets = self.search([('state', '=', 'running')])
        today = fields.Date.context_today(self)
        created = 0
        for asset in assets:
            try:
                posted_dates = set()
                for move in asset.depreciation_move_ids:
                    if move.state == 'posted':
                        posted_dates.add((move.date.year, move.date.month))
                for entry in asset._compute_depreciation_board():
                    if entry['date'] > today or (entry['date'].year, entry['date'].month) in posted_dates:
                        continue
                    asset._post_depreciation_entry(entry['date'], entry['amount'])
                    created += 1
            except Exception:
                _logger.exception(
                    "Depreciation entry failed for asset %s (id %s); skipping.",
                    asset.display_name, asset.id)
                self.env.cr.rollback()
                continue
        return created

    def _post_depreciation_entry(self, entry_date, amount):
        self.ensure_one()
        if self.asset_type == 'purchase':
            lines = [
                (0, 0, {
                    'name': _('Depreciation: %s', self.name),
                    'account_id': self.account_depreciation_id.id,
                    'debit': amount, 'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Depreciation: %s', self.name),
                    'account_id': self.account_asset_id.id,
                    'debit': 0.0, 'credit': amount,
                }),
            ]
        else:
            lines = [
                (0, 0, {
                    'name': _('Amortization: %s', self.name),
                    'account_id': self.account_asset_id.id,
                    'debit': amount, 'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Amortization: %s', self.name),
                    'account_id': self.account_depreciation_id.id,
                    'debit': 0.0, 'credit': amount,
                }),
            ]
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'date': entry_date,
            'ref': _('Depreciation: %s (%s)', self.name, entry_date.strftime('%b %Y')),
            'hadir_asset_id': self.id,
            'line_ids': lines,
        })
        move.action_post()
        return move

    # -----------------------------------------------------------------
    # Guards
    # -----------------------------------------------------------------

    def write(self, vals):
        locked = [f for f in ASSET_LOCKED_FIELDS if f in vals]
        if locked and any(asset.state != 'draft' for asset in self):
            raise UserError(_(
                "Only draft assets can be modified on: %s.", ', '.join(locked)))
        return super().write(vals)

    def unlink(self):
        if any(asset.state != 'draft' for asset in self):
            raise UserError(_("Only draft assets can be deleted."))
        return super().unlink()


class HadirAssetDispose(models.TransientModel):
    _name = 'hadir.asset.dispose'
    _description = 'Asset Disposal'

    asset_id = fields.Many2one('account.asset', required=True, readonly=True)
    company_id = fields.Many2one(related='asset_id.company_id')
    disposal_date = fields.Date(required=True, default=fields.Date.today)
    gain_loss_account_id = fields.Many2one(
        'account.account', string='Gain/Loss Account', required=True,
        check_company=True,
        help="The remaining book value is written off on this P&L account.")
    book_value = fields.Monetary(related='asset_id.book_value')
    currency_id = fields.Many2one(related='asset_id.currency_id')

    def action_dispose(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state != 'running':
            raise UserError(_("Only running assets can be disposed."))
        # drop not-yet-posted depreciation entries after the disposal date
        asset.depreciation_move_ids.filtered(
            lambda m: m.state == 'draft' and m.date and m.date > self.disposal_date
        ).unlink()
        if self.book_value:
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': asset.journal_id.id,
                'company_id': asset.company_id.id,
                'date': self.disposal_date,
                'ref': _('Disposal: %s', asset.name),
                'line_ids': [
                    (0, 0, {
                        'name': _('Disposal: %s', asset.name),
                        'account_id': self.gain_loss_account_id.id,
                        'debit': self.book_value, 'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': _('Disposal: %s', asset.name),
                        'account_id': asset.account_asset_id.id,
                        'debit': 0.0, 'credit': self.book_value,
                    }),
                ],
            })
            move.action_post()
        asset.write({'state': 'closed'})
        return {'type': 'ir.actions.act_window_close'}
