import logging
import os
from datetime import datetime

import requests

from odoo import _, api, models
from odoo.tools import format_datetime

_logger = logging.getLogger(__name__)
PARAM = 'technoai_taskhub.%s'
DOWN = ('qr', 'idle', 'logged_out', 'error', 'offline')


class TaskhubWaBot(models.AbstractModel):
    """ The Techno AI WhatsApp bot: one company number, linked like WhatsApp Web, that sends the alerts.

    The bot is a separate service (services/wa-bot) on the private Docker network. Its address and key
    come from the server environment (TECHNOAI_WA_BOT_URL / TECHNOAI_WA_BOT_KEY), so nobody types them
    into the ERP; the system parameters of the same names are only a fallback for local setups.
    """
    _name = 'taskhub.wa.bot'
    _description = 'Techno AI WhatsApp bot'

    @api.model
    def _conf(self):
        params = self.env['ir.config_parameter'].sudo()
        url = os.environ.get('TECHNOAI_WA_BOT_URL') or params.get_param(PARAM % 'wa_bot_url') or 'http://wa-bot:3000'
        key = os.environ.get('TECHNOAI_WA_BOT_KEY') or params.get_param(PARAM % 'wa_bot_key') or ''
        return url.rstrip('/'), key

    @api.model
    def _call(self, method, path, payload=None, timeout=4):
        """ Returns (http status, json body); status 0 when the bot cannot be reached. """
        url, key = self._conf()
        if not key:
            return 0, {'error': _('The bot key is not set on the server.')}
        try:
            response = requests.request(method, url + path, json=payload, timeout=timeout, headers={'X-Bot-Key': key})
        except requests.RequestException as error:
            _logger.info('Techno AI WhatsApp bot unreachable: %s', error)
            return 0, {'error': _('The WhatsApp bot is not running.')}
        try:
            body = response.json()
        except ValueError:
            body = {}
        return response.status_code, body

    @api.model
    def _status(self):
        code, body = self._call('GET', '/status')
        if code != 200:
            return {'status': 'offline', 'error': body.get('error') or _('The WhatsApp bot did not answer.')}
        return body

    @api.model
    def _send(self, digits, text):
        """ Returns (sent, info) like the other WhatsApp providers. """
        code, body = self._call('POST', '/send', {'phone': digits, 'message': text}, timeout=12)
        if code == 200 and body.get('ok'):
            return True, _('WhatsApp to +%s', digits)
        return False, _('WhatsApp bot: %s', body.get('error') or _('no answer'))

    @api.model
    def _logout(self):
        code, body = self._call('POST', '/logout', timeout=10)
        return code == 200, body.get('error')

    @api.model
    def _since_label(self, iso):
        if not iso:
            return ''
        try:
            moment = datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            return ''
        return format_datetime(self.env, moment, dt_format='d MMM y, HH:mm')

    @api.model
    def _cron_watch(self):
        """ Tell the administrators when the number stops working, and when it works again. """
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param(PARAM % 'whatsapp_provider') != 'bot':
            return
        state = self._status().get('status')
        before = params.get_param(PARAM % 'wa_bot_last_state')
        now = 'down' if state in DOWN else ('connected' if state == 'connected' else before)
        if now == before or not now:
            return
        params.set_param(PARAM % 'wa_bot_last_state', now)
        if not before and now == 'down':
            return  # never linked yet: nothing stopped
        admins = self.env.ref('base.group_system').sudo().users.filtered(lambda u: not u.share and u.active)
        if not admins:
            return
        if now == 'down':
            subject = _('WhatsApp alerts stopped')
            body = _('The company WhatsApp number is no longer linked, so RFQ alerts are not reaching WhatsApp. '
                     'Open Settings > Task Hub > WhatsApp dispatch and scan the QR code again. Browser alerts keep working.')
        else:
            subject = _('WhatsApp alerts are working again')
            body = _('The company WhatsApp number is linked again.')
        self.env.company.partner_id.sudo().with_context(mail_notify_author=True).message_notify(
            author_id=self.env.ref('base.partner_root').id,
            partner_ids=admins.partner_id.ids,
            subject=subject,
            body=body,
            subtype_xmlid='mail.mt_comment',
            email_layout_xmlid='mail.mail_notification_light',
        )
