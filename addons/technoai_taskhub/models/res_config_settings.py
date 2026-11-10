import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    taskhub_whatsapp_provider = fields.Selection(
        [('link', 'Open WhatsApp, message ready'),
         ('bot', 'Own number (Techno AI bot)'),
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

    # live state of the Techno AI WhatsApp bot, read from the bot when the settings open
    taskhub_wa_bot_state = fields.Selection(
        [('connected', 'Connected'), ('qr', 'Waiting for scan'), ('starting', 'Getting a code… press Refresh'),
         ('idle', 'Code expired, press Refresh'),
         ('reconnecting', 'Reconnecting'), ('logged_out', 'Logged out'), ('error', 'Error'), ('offline', 'Bot not running')],
        compute='_compute_taskhub_wa_bot')
    taskhub_wa_bot_qr = fields.Binary(compute='_compute_taskhub_wa_bot')
    taskhub_wa_bot_number = fields.Char(compute='_compute_taskhub_wa_bot')
    taskhub_wa_bot_since = fields.Char(compute='_compute_taskhub_wa_bot')
    taskhub_wa_bot_today = fields.Char(compute='_compute_taskhub_wa_bot')
    taskhub_wa_bot_error = fields.Char(compute='_compute_taskhub_wa_bot')
    # the provider actually in use: a choice made on the screen only counts once Save is pressed
    # (a default, not a compute: the settings form gets defaults when it opens, but not dependency-less computes)
    taskhub_wa_saved_provider = fields.Char(default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
        'technoai_taskhub.whatsapp_provider', 'link'), readonly=True)

    taskhub_rfq_mailbox = fields.Boolean('Read RFQ emails from a mailbox', config_parameter='technoai_taskhub.rfq_mailbox')
    taskhub_imap_host = fields.Char('IMAP server', config_parameter='technoai_taskhub.imap_host', default='imap.gmail.com')
    taskhub_imap_port = fields.Integer('IMAP port', config_parameter='technoai_taskhub.imap_port', default=993)
    taskhub_imap_user = fields.Char('Mailbox login', config_parameter='technoai_taskhub.imap_user')
    taskhub_imap_password = fields.Char('Mailbox password', config_parameter='technoai_taskhub.imap_password')

    @api.depends('taskhub_whatsapp_provider')
    def _compute_taskhub_wa_bot(self):
        bot = self.env['taskhub.wa.bot']
        for settings in self:
            values = dict.fromkeys(['taskhub_wa_bot_state', 'taskhub_wa_bot_qr', 'taskhub_wa_bot_number', 'taskhub_wa_bot_since',
                                    'taskhub_wa_bot_today', 'taskhub_wa_bot_error'], False)
            if settings.taskhub_whatsapp_provider == 'bot' and self.env.user.has_group('base.group_system'):
                status = bot._status()
                state = status.get('status')
                qr = status.get('qr') or ''
                values.update({
                    'taskhub_wa_bot_state': state if state in dict(self._fields['taskhub_wa_bot_state'].selection) else 'starting',
                    'taskhub_wa_bot_qr': qr.split(',', 1)[1].encode() if qr.startswith('data:image/png;base64,') else False,
                    'taskhub_wa_bot_number': status.get('me') or False,
                    'taskhub_wa_bot_since': bot._since_label(status.get('since')) if state == 'connected' else False,
                    'taskhub_wa_bot_today': _('%(sent)s sent · %(failed)s failed · limit %(limit)s', sent=status.get('sent_today', 0),
                                              failed=status.get('failed_today', 0), limit=status.get('max_per_day', 0))
                                            if state == 'connected' else False,
                    'taskhub_wa_bot_error': status.get('error') if state not in ('connected', 'qr') else False,
                })
            settings.update(values)

    def _taskhub_reload(self):
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_taskhub_wa_bot_refresh(self):
        return self._taskhub_reload()

    def action_taskhub_wa_bot_test(self):
        user = self.env.user
        employee = user.employee_ids[:1]
        number = employee.mobile_phone or user.partner_id.mobile or user.partner_id.phone
        if not number:
            raise UserError(_('Add your mobile number to your employee or contact first; the test goes to it.'))
        dispatch = self.env['taskhub.dispatch'].new({'phone': number, 'message': _(
            'Techno AI test: WhatsApp alerts from the company number are working.')})
        sent, info = self.env['taskhub.wa.bot']._send(dispatch._clean_phone(), dispatch.message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success' if sent else 'danger', 'title': _('WhatsApp test'),
                       'message': info if not sent else _('Sent to %s. Check your WhatsApp.', number), 'sticky': not sent},
        }

    def action_taskhub_wa_bot_unlink(self):
        done, error = self.env['taskhub.wa.bot']._logout()
        if not done:
            raise UserError(error or _('The WhatsApp bot did not answer.'))
        return self._taskhub_reload()

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
