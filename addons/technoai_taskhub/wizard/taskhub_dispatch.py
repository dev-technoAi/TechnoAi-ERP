import base64
import logging
import re
from urllib.parse import quote

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)
TIMEOUT = 10


class TaskhubDispatch(models.TransientModel):
    """ Send a task to its assignee by Techno AI notification, email and WhatsApp. """
    _name = 'taskhub.dispatch'
    _description = 'Dispatch a task'

    task_id = fields.Many2one('taskhub.task', required=True, ondelete='cascade')
    user_id = fields.Many2one(related='task_id.user_id', string='Assigned to')
    email = fields.Char('Email address')
    phone = fields.Char('WhatsApp number')
    via_notification = fields.Boolean('Techno AI notification', default=True)
    via_email = fields.Boolean('Email', default=True)
    via_whatsapp = fields.Boolean('WhatsApp')
    message = fields.Text(required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        task = self.env['taskhub.task'].browse(values.get('task_id') or self.env.context.get('active_id'))
        if task:
            employee = task.user_id.employee_ids[:1]
            values.update({
                'task_id': task.id,
                'email': task.user_id.email,
                'phone': employee.mobile_phone or task.user_id.partner_id.mobile or task.user_id.partner_id.phone,
                'via_whatsapp': bool(employee.mobile_phone or task.user_id.partner_id.mobile),
                'message': task._dispatch_text(),
            })
        return values

    def action_send(self):
        self.ensure_one()
        task = self.task_id
        if not task.user_id:
            raise UserError(_('Assign the task to someone before dispatching it.'))
        done = []
        if self.via_notification:
            task.message_post(body=plaintext2html(self.message), partner_ids=task.user_id.partner_id.ids,
                              subtype_xmlid='mail.mt_comment')
            done.append(_('Techno AI notification'))
        if self.via_email:
            if not self.email:
                raise UserError(_('%s has no email address.', task.user_id.name))
            # queued: the mail queue sends it with the outgoing mail server
            self.env['mail.mail'].sudo().create({
                'subject': _('Task: %s', task.name),
                'body_html': plaintext2html(self.message),
                'email_to': self.email,
                'email_from': self.env.user.email_formatted or self.env.company.email_formatted,
                'model': task._name,
                'res_id': task.id,
                'auto_delete': True,
            })
            done.append(_('email'))
        action = False
        if self.via_whatsapp:
            if not self.phone:
                raise UserError(_('Add a WhatsApp number for %s.', task.user_id.name))
            sent, info = self._send_whatsapp()
            if sent:
                done.append(info)
            else:
                # no provider, or the provider failed: open WhatsApp with the message ready to send
                action = {'type': 'ir.actions.act_url', 'url': self._whatsapp_link(), 'target': 'new'}
                done.append(_('WhatsApp (opened to send)'))
                if info:
                    task.message_post(body=info, message_type='notification', subtype_xmlid='mail.mt_note')
        task.message_post(body=_('Dispatched via %s.', ', '.join(done)), subtype_xmlid='mail.mt_note')
        return action or {'type': 'ir.actions.act_window_close'}

    # ------------------------------------------------------------------
    # WhatsApp
    # ------------------------------------------------------------------

    def _clean_phone(self):
        return re.sub(r'\D', '', self.phone or '').lstrip('0')

    def _whatsapp_link(self):
        return 'https://wa.me/%s?text=%s' % (self._clean_phone(), quote(self.message))

    def _send_whatsapp(self):
        """ Send through the provider set in Task Hub settings; returns (sent, info). """
        params = self.env['ir.config_parameter'].sudo()
        provider = params.get_param('technoai_taskhub.whatsapp_provider', 'link')
        phone = self._clean_phone()
        try:
            if provider == 'cloud':
                token = params.get_param('technoai_taskhub.wa_cloud_token')
                phone_id = params.get_param('technoai_taskhub.wa_cloud_phone_id')
                if not (token and phone_id):
                    return False, _('WhatsApp Cloud API is not configured.')
                response = requests.post(
                    'https://graph.facebook.com/v21.0/%s/messages' % phone_id, timeout=TIMEOUT,
                    headers={'Authorization': 'Bearer %s' % token},
                    json={'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': phone,
                          'type': 'text', 'text': {'preview_url': True, 'body': self.message}})
            elif provider == 'twilio':
                sid = params.get_param('technoai_taskhub.wa_twilio_sid')
                token = params.get_param('technoai_taskhub.wa_twilio_token')
                sender = params.get_param('technoai_taskhub.wa_twilio_from')
                if not (sid and token and sender):
                    return False, _('Twilio is not configured.')
                auth = base64.b64encode(('%s:%s' % (sid, token)).encode()).decode()
                response = requests.post(
                    'https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json' % sid, timeout=TIMEOUT,
                    headers={'Authorization': 'Basic %s' % auth},
                    data={'From': sender if sender.startswith('whatsapp:') else 'whatsapp:%s' % sender,
                          'To': 'whatsapp:+%s' % phone, 'Body': self.message})
            elif provider == 'green':
                instance = params.get_param('technoai_taskhub.wa_green_instance')
                token = params.get_param('technoai_taskhub.wa_green_token')
                if not (instance and token):
                    return False, _('Green API is not configured.')
                response = requests.post(
                    'https://api.green-api.com/waInstance%s/sendMessage/%s' % (instance, token), timeout=TIMEOUT,
                    json={'chatId': '%s@c.us' % phone, 'message': self.message})
            else:
                return False, ''
        except requests.RequestException as error:
            _logger.warning('Task Hub WhatsApp dispatch failed: %s', error)
            return False, _('WhatsApp could not be reached (%s); the message opened in WhatsApp instead.', provider)
        if response.ok:
            return True, _('WhatsApp to +%s', phone)
        _logger.warning('Task Hub WhatsApp dispatch refused (%s): %s', response.status_code, response.text[:300])
        return False, _('WhatsApp (%(provider)s) refused the message (%(code)s); it opened in WhatsApp instead.',
                        provider=provider, code=response.status_code)
