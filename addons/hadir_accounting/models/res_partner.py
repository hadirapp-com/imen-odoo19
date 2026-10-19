from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.tools import formatLang


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # res.partner has no currency_id of its own; monetary widgets need one
    hadir_currency_id = fields.Many2one(
        'res.currency', string='Follow-up Currency',
        compute='_compute_hadir_currency', compute_sudo=True)
    hadir_total_due = fields.Monetary(
        string='Total Due (Follow-up)', default=0.0,
        currency_field='hadir_currency_id')
    hadir_overdue_amount = fields.Monetary(
        string='Overdue Amount (Follow-up)', default=0.0, index=True,
        currency_field='hadir_currency_id')
    hadir_max_overdue_days = fields.Integer(string='Max Overdue Days', default=0)
    hadir_followup_level_id = fields.Many2one(
        'hadir.followup.level', string='Follow-up Level (Hadir)', compute_sudo=True)
    hadir_last_followup_level_id = fields.Many2one('hadir.followup.level', string='Last Follow-up Level', copy=False)
    hadir_last_followup_date = fields.Date(string='Last Follow-up Date', copy=False)
    hadir_followup_excluded = fields.Boolean(
        string='No Follow-up',
        help="Exclude this partner from automatic follow-ups.")

    # -----------------------------------------------------------------
    # Recompute (fields are plain columns refreshed on open / by cron)
    # -----------------------------------------------------------------

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_hadir_currency(self):
        for partner in self:
            partner.hadir_currency_id = (
                partner.company_id or self.env.company).currency_id

    @api.model
    def _hadir_recompute_followup(self):
        """Refresh follow-up figures for the current company; returns the
        affected partners."""
        company = self.env.company
        today = fields.Date.context_today(self)
        aml = self.env['account.move.line']
        base = [
            ('account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('company_id', '=', company.id),
            ('partner_id', '!=', False),
        ]

        def read_partner_groups(domain, aggregates):
            result = {}
            groups = aml._read_group(domain, ['partner_id'], aggregates)
            for row in groups:
                partner = row[0]
                result[partner.id] = row[1:]
            return result

        totals = read_partner_groups(base, ['amount_residual:sum'])
        overdue = read_partner_groups(base + [('date_maturity', '<', today)],
                                      ['amount_residual:sum', 'date_maturity:min'])

        levels = self.env['hadir.followup.level'].search(
            [('company_id', 'in', (False, company.id))])
        # include partners previously flagged so they can be reset to zero
        partner_ids = set(totals) | set(overdue) | set(
            self.search([('hadir_total_due', '!=', 0.0),
                         ('hadir_overdue_amount', '!=', 0.0)]).ids)

        partners = self.browse(list(partner_ids))
        states = {p.id: (p.hadir_followup_excluded,) for p in partners}
        to_write = {}
        for pid in partner_ids:
            total_due = totals.get(pid, (0.0,))[0] or 0.0
            overdue_amount, min_maturity = overdue.get(pid, (0.0, False))
            max_days = (today - min_maturity).days if min_maturity else 0
            level = False
            if overdue_amount and not states[pid][0]:
                matching = levels.filtered(lambda l: l.delay_days <= max_days)
                level = matching[-1] if matching else False
            to_write[pid] = {
                'hadir_total_due': total_due,
                'hadir_overdue_amount': overdue_amount or 0.0,
                'hadir_max_overdue_days': max_days if overdue_amount else 0,
                'hadir_followup_level_id': level.id if level else False,
            }
        # batch partners sharing identical values, skip real no-ops
        groups = defaultdict(list)
        for pid, vals in to_write.items():
            groups[tuple(vals.items())].append(pid)
        for vals_items, pids in groups.items():
            vals = dict(vals_items)
            changed = self.browse([])
            for partner in self.browse(pids):
                for f, v in vals.items():
                    current = partner[f]
                    if isinstance(current, models.BaseModel):
                        current = current.id
                    if current != v:
                        changed |= partner
                        break
            if changed:
                changed.write(vals)
        return partners

    def action_hadir_process_followups(self):
        """Refresh figures then open the follow-up list."""
        self._hadir_recompute_followup()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Follow-ups'),
            'res_model': 'res.partner',
            'view_mode': 'tree,form',
            'domain': [('hadir_overdue_amount', '>', 0)],
            'context': {
                'search_default_hadir_followup_filter': 1,
                'default_is_customer': True,
            },
            'views': [(self.env.ref('hadir_accounting.view_partner_hadir_followup_tree').id, 'tree'),
                      (False, 'form')],
        }

    # -----------------------------------------------------------------
    # Sending
    # -----------------------------------------------------------------

    def action_hadir_send_followup(self):
        sent = 0
        for partner in self:
            if partner._hadir_send_followup_mail():
                sent += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Follow-up'),
                'message': _('%s reminder email(s) queued/sent.', sent),
                'type': 'success',
            },
        }

    def _hadir_send_followup_mail(self, level=None):
        self.ensure_one()
        if self.hadir_followup_excluded:
            return False
        level = level or self.hadir_followup_level_id
        if not level:
            return False
        template = level.email_template_id or self.env.ref(
            'hadir_accounting.mail_template_hadir_followup_default',
            raise_if_not_found=False)
        if template:
            template.with_company(self.env.company).send_mail(
                self.id, force_send=True)
        today = fields.Date.context_today(self)
        self.write({
            'hadir_last_followup_level_id': level.id,
            'hadir_last_followup_date': today,
        })
        if level.create_activity:
            activity_type = self.env.ref('mail.mail_activity_data_email',
                                         raise_if_not_found=False)
            self.env['mail.activity'].create({
                'res_model_id': self.env['ir.model']._get_id('res.partner'),
                'res_id': self.id,
                'activity_type_id': activity_type.id if activity_type else False,
                'summary': _('Follow-up: %s', level.name),
                'note': level.notes or '',
                'date_deadline': today + timedelta(days=7),
                'user_id': self.env.user.id,
            })
        return True

    # -----------------------------------------------------------------
    # Overdue details (used in the email template)
    # -----------------------------------------------------------------

    def hadir_get_overdue_lines_html(self):
        self.ensure_one()
        company = self.env.company
        today = fields.Date.context_today(self)
        amls = self.env['account.move.line'].search([
            ('partner_id', '=', self.id),
            ('account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('company_id', '=', company.id),
            ('date_maturity', '<', today),
        ], order='date_maturity')
        rows = []
        for aml in amls:
            days = (today - aml.date_maturity).days
            rows.append(
                '<tr><td>%s</td><td>%s</td><td class="text-end">%s</td>'
                '<td class="text-end">%s</td></tr>' % (
                    aml.move_id.name or '',
                    aml.date_maturity.strftime('%d %b %Y'),
                    _('%s days', days),
                    formatLang(self.env, aml.amount_residual,
                               currency_obj=aml.company_id.currency_id)))
        return (
            '<table class="table table-sm" style="width:100%%">'
            '<thead><tr><th>%s</th><th>%s</th><th class="text-end">%s</th>'
            '<th class="text-end">%s</th></tr></thead><tbody>%s</tbody></table>'
            % (_('Invoice'), _('Due Date'), _('Overdue'), _('Amount'),
               ''.join(rows)))
