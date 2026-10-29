from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    taskhub_whatsapp_provider = fields.Selection(
        [('link', 'WhatsApp link (no account needed)'),
         ('cloud', 'WhatsApp Cloud API (Meta)'),
         ('twilio', 'Twilio'),
         ('green', 'Green API')],
        'WhatsApp provider', default='link', config_parameter='technoai_taskhub.whatsapp_provider')
    taskhub_wa_cloud_token = fields.Char('Cloud API access token', config_parameter='technoai_taskhub.wa_cloud_token')
    taskhub_wa_cloud_phone_id = fields.Char('Cloud API phone number ID', config_parameter='technoai_taskhub.wa_cloud_phone_id')
    taskhub_wa_twilio_sid = fields.Char('Twilio account SID', config_parameter='technoai_taskhub.wa_twilio_sid')
    taskhub_wa_twilio_token = fields.Char('Twilio auth token', config_parameter='technoai_taskhub.wa_twilio_token')
    taskhub_wa_twilio_from = fields.Char('Twilio WhatsApp number', config_parameter='technoai_taskhub.wa_twilio_from')
    taskhub_wa_green_instance = fields.Char('Green API instance ID', config_parameter='technoai_taskhub.wa_green_instance')
    taskhub_wa_green_token = fields.Char('Green API token', config_parameter='technoai_taskhub.wa_green_token')

    taskhub_rfq_mailbox = fields.Boolean('Read RFQ emails from a mailbox', config_parameter='technoai_taskhub.rfq_mailbox')
    taskhub_imap_host = fields.Char('IMAP server', config_parameter='technoai_taskhub.imap_host', default='imap.gmail.com')
    taskhub_imap_port = fields.Integer('IMAP port', config_parameter='technoai_taskhub.imap_port', default=993)
    taskhub_imap_user = fields.Char('Mailbox login', config_parameter='technoai_taskhub.imap_user')
    taskhub_imap_password = fields.Char('Mailbox password', config_parameter='technoai_taskhub.imap_password')

    def action_taskhub_test_mailbox(self):
        self.execute()
        mailbox = self.env['taskhub.mailbox']
        settings = mailbox._settings()
        try:
            imap = mailbox._connect(settings)
            imap.select('INBOX', readonly=True)
            imap.logout()
        except Exception as error:
            message, kind = str(error), 'danger'
        else:
            message, kind = _('Connected to %s.', settings['user']), 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': kind, 'title': _('RFQ mailbox'), 'message': message, 'sticky': kind == 'danger'},
        }
