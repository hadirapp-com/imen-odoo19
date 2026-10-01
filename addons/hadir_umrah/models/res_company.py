from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    umrah_whatsapp_provider = fields.Selection(
        selection=[
            ('log', 'Log only (testing)'),
            ('http', 'Generic HTTP API'),
        ],
        string='WhatsApp Provider', default='log', required=True,
        help='Provider used to deliver queued WhatsApp notifications. '
             '"Log only" marks messages as sent and writes them to the server '
             'log. "Generic HTTP API" posts {target, message} JSON to the '
             'configured URL with the token in the Authorization header, '
             'which covers most WhatsApp gateway services. Custom providers '
             'can override _prepare_provider_payload() / '
             '_process_provider_response().')
    umrah_whatsapp_api_url = fields.Char(string='WhatsApp API URL')
    umrah_whatsapp_api_token = fields.Char(
        string='WhatsApp API Token', groups='base.group_system')
