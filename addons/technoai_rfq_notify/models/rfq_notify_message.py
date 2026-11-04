import logging
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.tools import email_normalize, html2plaintext

_logger = logging.getLogger(__name__)


class RfqNotifyMessage(models.Model):
    """ An email of an employee's mailbox kept in the ERP: an RFQ, a later email of that client, or a reply sent from here. """
    _name = 'rfq.notify.message'
    _description = 'RFQ email'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _rec_name = 'subject'

    mailbox_id = fields.Many2one('rfq.notify.mailbox', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one(related='mailbox_id.user_id', string='Employee', store=True, index=True)
    mailbox_email = fields.Char(related='mailbox_id.email', string='Mailbox email')
    kind = fields.Selection([('rfq', 'New RFQ'), ('client', 'Client email'), ('sent', 'Sent from the ERP')],
                            required=True, default='rfq', string='Type')
    direction = fields.Selection([('in', 'Received'), ('out', 'Sent')], compute='_compute_direction', store=True)
    is_test = fields.Boolean()
    message_id = fields.Char('Message-ID', index=True, copy=False)
    references = fields.Char(copy=False)
    parent_id = fields.Many2one('rfq.notify.message', 'Reply to', ondelete='set null', index=True)
    root_id = fields.Many2one('rfq.notify.message', 'Conversation', compute='_compute_root_id', store=True, recursive=True, index=True)
    subject = fields.Char()
    email_from = fields.Char('From')
    email_to = fields.Char('To')
    email_cc = fields.Char('Cc')
    date = fields.Datetime('Received', default=fields.Datetime.now, index=True)
    body_html = fields.Html('Email', sanitize_style=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    client_key = fields.Char('Client', index=True, help='The domain of the client, or their address when they write from a public email service.')
    client_name = fields.Char(compute='_compute_client_name')
    taskhub_rfq_id = fields.Many2one('taskhub.rfq', 'Task Hub RFQ', ondelete='set null')
    taskhub_quotation_id = fields.Many2one('taskhub.quotation', compute='_compute_taskhub_quotation_id')
    opened_date = fields.Datetime('Opened', readonly=True, copy=False)
    browser_state = fields.Selection([('none', 'Off'), ('sent', 'Sent')], default='none', readonly=True, string='Browser')
    browser_state_label = fields.Char(compute='_compute_browser_state_label')
    whatsapp_state = fields.Selection([('none', 'Off'), ('sent', 'Delivered'), ('failed', 'Failed')], default='none',
                                      readonly=True, string='WhatsApp')
    whatsapp_info = fields.Char(readonly=True)
    reminder_level = fields.Integer(readonly=True, copy=False, help='1: the owner was reminded, 2: their manager was told.')
    conversation_html = fields.Html(compute='_compute_conversation_html', sanitize=False)
    conversation_count = fields.Integer(compute='_compute_conversation_html')
    client_message_ids = fields.Many2many('rfq.notify.message', compute='_compute_client_message_ids')

    @api.depends('kind')
    def _compute_direction(self):
        for message in self:
            message.direction = 'out' if message.kind == 'sent' else 'in'

    @api.depends('parent_id', 'parent_id.root_id')
    def _compute_root_id(self):
        for message in self:
            message.root_id = message.parent_id.root_id or message.parent_id or message

    def _compute_client_name(self):
        for message in self:
            partner = message.taskhub_rfq_id.partner_id
            message.client_name = partner.name or message.taskhub_rfq_id.client_name or message.client_key

    def _compute_taskhub_quotation_id(self):
        for message in self:
            message.taskhub_quotation_id = message.taskhub_rfq_id.quotation_ids.sorted('id', reverse=True)[:1]

    def _compute_browser_state_label(self):
        labels = dict(self._fields['browser_state'].selection)
        for message in self:
            message.browser_state_label = labels.get(message.browser_state)

    def _conversation(self):
        self.ensure_one()
        root = self.root_id or self
        return self.search([('root_id', '=', root.id)], order='date asc, id asc') | root

    def _compute_conversation_html(self):
        for message in self:
            thread = message._conversation().sorted(lambda m: (m.date or fields.Datetime.now(), m.id))
            parts = []
            for mail in thread:
                files = Markup('').join(
                    Markup('<a class="o_rfqn_file" href="/web/content/%s?download=true"><i class="fa fa-paperclip"></i> %s</a>')
                    % (attachment.id, attachment.name) for attachment in mail.attachment_ids)
                parts.append(Markup(
                    '<div class="o_rfqn_mail%s"><div class="o_rfqn_head"><b>%s</b><span>%s</span><br/>'
                    '<small>%s %s%s</small></div><div class="o_rfqn_body">%s</div>%s</div>') % (
                    ' o_rfqn_sent' if mail.kind == 'sent' else '',
                    mail.email_from or '',
                    fields.Datetime.context_timestamp(mail, mail.date).strftime('%d %b %Y %H:%M') if mail.date else '',
                    _('to'), mail.email_to or '',
                    (Markup(' &middot; cc %s') % mail.email_cc) if mail.email_cc else '',
                    mail.body_html or '',
                    Markup('<div class="o_rfqn_files">%s</div>') % files if files else ''))
            message.conversation_html = Markup('').join(parts)
            message.conversation_count = len(thread)

    def _compute_client_message_ids(self):
        for message in self:
            if not message.client_key:
                message.client_message_ids = False
                continue
            others = self.search([('mailbox_id', '=', message.mailbox_id.id), ('client_key', '=', message.client_key),
                                  ('kind', '!=', 'sent'), ('id', 'not in', message._conversation().ids)], limit=30)
            message.client_message_ids = others

    # ------------------------------------------------------------------
    # Opening: the alert counts as seen once its owner opens it
    # ------------------------------------------------------------------

    def web_read(self, specification):
        if len(self) == 1 and not self.opened_date and self.user_id == self.env.user:
            self.sudo().opened_date = fields.Datetime.now()
        return super().web_read(specification)

    # ------------------------------------------------------------------
    # Task Hub
    # ------------------------------------------------------------------

    def _link_taskhub_rfq(self, raw):
        """ The Email RFQ in Task Hub: the one the shared RFQ mailbox already made, or a new one for this employee. """
        self.ensure_one()
        Rfq = self.env['taskhub.rfq'].sudo()
        known = self.message_id and self.env['mail.message'].sudo().search(
            [('message_id', '=', self.message_id), ('model', '=', 'taskhub.rfq')], limit=1)
        if known:
            self.taskhub_rfq_id = Rfq.browse(known.res_id).exists()
            return
        try:
            with self.env.cr.savepoint():
                rfq_id = self.env['mail.thread'].sudo().message_process('taskhub.rfq', raw, save_original=False)
            rfq = Rfq.browse(rfq_id).exists()
            if rfq and not rfq.user_id:
                rfq.user_id = self.user_id
            self.taskhub_rfq_id = rfq
        except Exception:
            _logger.exception('RFQ notification: could not create the Task Hub RFQ for %s', self.message_id)

    def _save_attachments(self, attachments):
        self.ensure_one()
        values = []
        for attachment in attachments:
            name, content = attachment[0], attachment[1]
            if isinstance(content, str):
                content = content.encode()
            if not content:
                continue
            values.append({'name': name or 'attachment', 'raw': content, 'res_model': self._name, 'res_id': self.id})
        if values:
            self.attachment_ids = self.env['ir.attachment'].sudo().create(values)

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _alert_text(self):
        self.ensure_one()
        title = _('New RFQ') if self.kind == 'rfq' else _('Email from an RFQ client')
        url = '%s/odoo/action-technoai_rfq_notify.rfq_notify_message_action/%s' % (self.get_base_url(), self.id)
        return title, _('%(title)s in your mailbox %(mailbox)s\nFrom: %(sender)s\nSubject: %(subject)s\nOpen: %(url)s',
                        title=title, mailbox=self.mailbox_email, sender=self.email_from or '', subject=self.subject or '', url=url)

    def _notify_owner(self, partners=None, reminder=False):
        """ Browser and phone push with the ERP inbox, then WhatsApp, as the mailbox owner chose. """
        for message in self:
            mailbox = message.mailbox_id
            title, text = message._alert_text()
            if reminder:
                title = _('Reminder: %s', title)
            recipients = partners or mailbox.user_id.partner_id
            if mailbox.notify_browser or partners:
                # from OdooBot, and notified even when the owner pressed the button (Odoo skips the current user otherwise)
                message.sudo().with_context(rfq_notify_inbox=True, mail_notify_author=True).message_notify(
                    author_id=self.env.ref('base.partner_root').id,
                    partner_ids=recipients.ids,
                    subject='%s: %s' % (title, message.subject or ''),
                    body=Markup('<p><b>%s</b><br/>%s<br/>%s</p>') % (
                        title, _('From: %s', message.email_from or ''), _('Subject: %s', message.subject or '')),
                    subtype_xmlid='mail.mt_comment',
                    email_layout_xmlid='mail.mail_notification_light',
                )
                message.browser_state = 'sent'
                # an open ERP tab rings, shows the alert and refreshes the alert list without a page reload
                for partner in recipients:
                    partner._bus_send('technoai_rfq_notify/alert', {
                        'id': message.id,
                        'title': title,
                        'subject': message.subject or '',
                        'sender': message.email_from or '',
                        'mailbox': mailbox.email,
                    })
            number =mailbox.whatsapp_number if not partners else (partners[:1].mobile or partners[:1].phone)
            if mailbox.notify_whatsapp and number:
                sent, info = self.env['taskhub.dispatch'].sudo().new({'phone': number, 'message': text})._send_whatsapp()
                message.write({'whatsapp_state': 'sent' if sent else 'failed',
                               'whatsapp_info': info or _('No WhatsApp provider is set in Task Hub settings.')})
            elif mailbox.notify_whatsapp and not reminder:
                message.write({'whatsapp_state': 'failed', 'whatsapp_info': _('No WhatsApp number on the mailbox.')})

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        """ Alerts always go to the ERP inbox (and so to web push), whatever email preference the employee has. """
        recipients = super()._notify_get_recipients(message, msg_vals=msg_vals, **kwargs)
        if self.env.context.get('rfq_notify_inbox'):
            for recipient in recipients:
                if recipient.get('active', True) and not recipient.get('share'):
                    recipient['notif'] = 'inbox'
        return recipients

    @api.model
    def _cron_remind(self):
        """ Remind the owner of an alert nobody opened; later, tell their manager. """
        params = self.env['ir.config_parameter'].sudo()
        minutes = int(params.get_param('technoai_rfq_notify.remind_minutes') or 15)
        if minutes <= 0:
            return
        now = fields.Datetime.now()
        base = [('direction', '=', 'in'), ('opened_date', '=', False), ('is_test', '=', False)]
        for message in self.sudo().search(base + [('reminder_level', '=', 0), ('create_date', '<', now - timedelta(minutes=minutes))]):
            message._notify_owner(reminder=True)
            message.reminder_level = 1
        if params.get_param('technoai_rfq_notify.escalate', 'True') != 'True':
            return
        for message in self.sudo().search(base + [('reminder_level', '=', 1), ('create_date', '<', now - timedelta(minutes=2 * minutes))]):
            employee = message.user_id.employee_ids[:1]
            manager = employee.parent_id.user_id
            if manager and manager != message.user_id:
                message._notify_owner(partners=manager.partner_id, reminder=True)
            message.reminder_level = 2

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def _open_composer(self, mode):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': {'reply': _('Reply'), 'reply_all': _('Reply all'), 'forward': _('Forward')}[mode],
            'res_model': 'rfq.notify.compose',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_message_id': self.id, 'default_mode': mode},
        }

    def action_reply(self):
        return self._open_composer('reply')

    def action_reply_all(self):
        return self._open_composer('reply_all')

    def action_forward(self):
        return self._open_composer('forward')

    def action_open_taskhub_rfq(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'taskhub.rfq', 'res_id': self.taskhub_rfq_id.id, 'view_mode': 'form'}

    def action_open_quotation(self):
        self.ensure_one()
        if self.taskhub_quotation_id:
            return self.taskhub_quotation_id._open_form()
        return self.taskhub_rfq_id.action_new_quotation()

    def action_open(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form'}

    @api.model
    def _sender_address(self, value):
        return email_normalize(value or '') or ''

    def _plain_body(self):
        self.ensure_one()
        return html2plaintext(self.body_html or '')

    def _quote_html(self):
        self.ensure_one()
        when = fields.Datetime.context_timestamp(self, self.date).strftime('%d %b %Y %H:%M') if self.date else ''
        return Markup('<br/><div style="color:#777;border-left:3px solid #ddd;padding-left:10px">%s<br/>%s</div>') % (
            _('On %(when)s, %(sender)s wrote:', when=when, sender=self.email_from or ''), self.body_html or escape(''))
