import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HadirFollowupLevel(models.Model):
    _name = 'hadir.followup.level'
    _description = 'Follow-up Level'
    _order = 'delay_days, id'
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)
    delay_days = fields.Integer(
        string='Overdue Days', required=True, default=15,
        help="This level applies to customers overdue by at least this "
             "number of days. The highest matching level wins.")
    email_template_id = fields.Many2one(
        'mail.template', string='Email Template',
        domain="[('model', '=', 'res.partner')]",
        default=lambda self: self.env.ref(
            'hadir_accounting.mail_template_hadir_followup_default',
            raise_if_not_found=False))
    auto_send = fields.Boolean(
        string='Send Automatically',
        help="Send the reminder email automatically once per level, via the "
             "daily Follow-up cron.")
    create_activity = fields.Boolean(string='Create Activity', default=True)
    notes = fields.Text(translate=True)

    @api.model
    def _cron_process_followups(self):
        today = fields.Date.context_today(self)
        count = 0
        for company in self.env['res.company'].search([]):
            partners = self.env['res.partner'].with_company(
                company)._hadir_recompute_followup()
            levels = self.search([
                ('auto_send', '=', True),
                ('company_id', 'in', (False, company.id))])
            for level in levels:
                targets = partners.filtered(
                    lambda p: not p.hadir_followup_excluded
                    and p.hadir_followup_level_id == level
                    and p.hadir_last_followup_level_id != level)
                for partner in targets:
                    if partner._hadir_send_followup_mail(level=level):
                        count += 1
        _logger.info('hadir_accounting follow-up cron: %s email(s) sent (as of %s)', count, today)
        return True
