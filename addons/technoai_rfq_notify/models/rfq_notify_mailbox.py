import email
import email.policy
import imaplib
import logging
import re
import smtplib
import ssl

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize, html2plaintext

from odoo.addons.technoai_taskhub.models.taskhub_mailbox import has_rfq_intent, is_non_rfq

_logger = logging.getLogger(__name__)

# a client writing from one of these is known by their address, not by the whole domain
PUBLIC_DOMAINS = {
    'gmail.com', 'googlemail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 'msn.com', 'icloud.com',
    'me.com', 'aol.com', 'proton.me', 'protonmail.com', 'yandex.com', 'zoho.com', 'zohomail.com', 'gmx.com', 'mail.com',
}
FETCH_LIMIT = 30


def client_key(address):
    """ "accounts@gulfhorizon.ae" -> "gulfhorizon.ae"; "ahmed@gmail.com" stays the full address. """
    address = email_normalize(address or '') or ''
    domain = address.rpartition('@')[2]
    return address if not domain or domain in PUBLIC_DOMAINS else domain


class RfqNotifyMailbox(models.Model):
    """ An employee's own mailbox, read-only: only RFQs and the emails of their RFQ clients come into the ERP. """
    _name = 'rfq.notify.mailbox'
    _description = 'RFQ notification mailbox'
    _order = 'user_id, email'
    _rec_name = 'email'

    email = fields.Char('Email address', required=True)
    user_id = fields.Many2one('res.users', 'Employee', required=True, default=lambda self: self.env.user,
                              domain=[('share', '=', False)], index=True)
    active = fields.Boolean(default=True)
    provider = fields.Selection([('zoho', 'Zoho Mail'), ('other', 'Other (IMAP/SMTP)')], default='zoho', required=True)
    password = fields.Char('App password', help='A Zoho application-specific password, not the login password.')
    imap_host = fields.Char('IMAP server', default='imap.zoho.com', required=True)
    imap_port = fields.Integer('IMAP port', default=993, required=True)
    smtp_host = fields.Char('SMTP server', default='smtp.zoho.com', required=True)
    smtp_port = fields.Integer('SMTP port', default=465, required=True)
    whatsapp_number = fields.Char('WhatsApp number for alerts')
    notify_browser = fields.Boolean('Browser / phone', default=True)
    notify_whatsapp = fields.Boolean('WhatsApp', default=True)
    create_taskhub_rfq = fields.Boolean('Also create the RFQ in Task Hub', default=True)
    signature = fields.Html('My email signature', sanitize_attributes=False,
                            help='Added to every email you send from the ERP. Text, links and images are kept.')
    state = fields.Selection([('new', 'Not checked yet'), ('ok', 'Connected'), ('error', 'Needs attention')],
                             default='new', readonly=True)
    last_error = fields.Char(readonly=True)
    last_check = fields.Datetime('Last checked', readonly=True)
    last_uid = fields.Integer(readonly=True, copy=False)
    uid_validity = fields.Char(readonly=True, copy=False)
    message_ids = fields.One2many('rfq.notify.message', 'mailbox_id')
    rfq_count = fields.Integer('RFQs (30 days)', compute='_compute_rfq_count')

    _sql_constraints = [('email_user_uniq', 'unique(email, user_id)', 'This mailbox is already added.')]

    def _compute_rfq_count(self):
        since = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        groups = self.env['rfq.notify.message']._read_group(
            [('mailbox_id', 'in', self.ids), ('kind', '=', 'rfq'), ('date', '>=', since)], ['mailbox_id'], ['__count'])
        counts = {mailbox.id: count for mailbox, count in groups}
        for mailbox in self:
            mailbox.rfq_count = counts.get(mailbox.id, 0)

    @api.onchange('provider')
    def _onchange_provider(self):
        if self.provider == 'zoho':
            self.update({'imap_host': 'imap.zoho.com', 'imap_port': 993, 'smtp_host': 'smtp.zoho.com', 'smtp_port': 465})

    @api.onchange('email', 'user_id')
    def _onchange_email(self):
        if self.email and not self.signature:
            user = self.user_id or self.env.user
            self.signature = user.signature or '<p><b>%s</b><br/>Techno AI<br/>%s</p>' % (user.name, self.email)

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    def _login_address(self):
        return (self.email or '').strip()

    def _imap(self):
        self.ensure_one()
        if not self.password:
            raise UserError(_('Add the app password of %s first.', self.email))
        if self.imap_port == 993:
            imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=20)
        else:
            imap = imaplib.IMAP4(self.imap_host, self.imap_port, timeout=20)
            imap.starttls()
        imap.login(self._login_address(), self.password)
        return imap

    def _smtp(self):
        self.ensure_one()
        if not self.password:
            raise UserError(_('Add the app password of %s first.', self.email))
        context = ssl.create_default_context()
        if self.smtp_port == 465:
            smtp = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30, context=context)
        else:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            smtp.starttls(context=context)
        smtp.login(self._login_address(), self.password)
        return smtp

    def action_test_connection(self):
        self.ensure_one()
        problems = []
        try:
            imap = self._imap()
            imap.logout()
        except (OSError, imaplib.IMAP4.error, UserError) as error:
            problems.append(_('Reading (IMAP %(host)s): %(error)s', host=self.imap_host, error=error))
        try:
            smtp = self._smtp()
            smtp.quit()
        except (OSError, smtplib.SMTPException, UserError) as error:
            problems.append(_('Sending (SMTP %(host)s): %(error)s', host=self.smtp_host, error=error))
        if problems:
            self.write({'state': 'error', 'last_error': ' | '.join(map(str, problems))[:500]})
            message, kind = '\n'.join(map(str, problems)) + '\n\n' + _(
                'In Zoho: turn on IMAP access (Settings > Mail Accounts), use an application-specific password, '
                'and check the server for your Zoho region (zoho.com, zoho.eu, zoho.in...).'), 'danger'
        else:
            self.write({'state': 'ok', 'last_error': False})
            message, kind = _('Reading and sending both work for %s.', self.email), 'success'
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': kind, 'title': _('Test connection'), 'message': message, 'sticky': kind == 'danger',
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    def action_test_alert(self):
        """ Send this mailbox's owner a sample alert on every channel that is turned on. """
        self.ensure_one()
        sample = self.env['rfq.notify.message'].create({
            'mailbox_id': self.id,
            'kind': 'rfq',
            'subject': _('Test alert: RFQ notifications work'),
            'email_from': self.email,
            'body_html': '<p>%s</p>' % _('This is a test of RFQ Mail Notification. Real RFQs will look like this.'),
            'is_test': True,
        })
        sample._notify_owner()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'info', 'title': _('Test alert sent'),
                       'message': _('Browser: %(browser)s. WhatsApp: %(wa)s.', browser=sample.browser_state_label,
                                    wa=sample.whatsapp_info or sample.whatsapp_state)},
        }

    def action_check_now(self):
        for mailbox in self:
            mailbox._check_mailbox()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @api.model
    def _cron_check_mailboxes(self):
        for mailbox in self.sudo().search([('active', '=', True), ('password', '!=', False)]):
            try:
                with self.env.cr.savepoint():
                    mailbox._check_mailbox()
            except Exception:
                _logger.exception('RFQ notification: could not check %s', mailbox.email)
            self.env.cr.commit()

    def _check_mailbox(self):
        """ Read the new emails of the inbox, read-only, and keep the RFQs and the RFQ clients' emails. """
        self.ensure_one()
        try:
            imap = self._imap()
        except (OSError, imaplib.IMAP4.error) as error:
            self.write({'state': 'error', 'last_error': str(error)[:500], 'last_check': fields.Datetime.now()})
            return 0
        kept = 0
        try:
            imap.select('INBOX', readonly=True)
            validity = (imap.response('UIDVALIDITY')[1] or [b''])[0]
            validity = validity.decode() if isinstance(validity, bytes) else str(validity or '')
            _status, data = imap.uid('search', None, 'ALL')
            uids = [int(uid) for uid in (data[0] or b'').split()]
            if not self.last_uid or validity != self.uid_validity:
                # first check (or the mailbox was rebuilt): start from now, without alerting about old emails
                self.write({'last_uid': max(uids or [0]), 'uid_validity': validity})
                uids = []
            new_uids = [uid for uid in uids if uid > self.last_uid][:FETCH_LIMIT]
            for uid in new_uids:
                _status, data = imap.uid('fetch', str(uid), '(BODY.PEEK[])')
                raw = next((part[1] for part in data if isinstance(part, tuple)), None)
                if raw:
                    try:
                        with self.env.cr.savepoint():
                            kept += bool(self._process_email(raw))
                    except Exception:
                        _logger.exception('RFQ notification: could not read email %s of %s', uid, self.email)
                self.last_uid = uid
            self.write({'state': 'ok', 'last_error': False, 'last_check': fields.Datetime.now()})
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        return kept

    def _process_email(self, raw):
        """ Keep the email when it is an RFQ, a reply in a kept conversation, or from a known RFQ client. """
        self.ensure_one()
        Message = self.env['rfq.notify.message'].sudo()
        message = email.message_from_bytes(raw, policy=email.policy.SMTP)
        parsed = self.env['mail.thread'].message_parse(message)
        message_id = parsed.get('message_id')
        if message_id and Message.search_count([('mailbox_id', '=', self.id), ('message_id', '=', message_id)]):
            return False
        sender = email_normalize(parsed.get('email_from') or '') or ''
        if sender == email_normalize(self.email):
            return False
        subject = parsed.get('subject') or ''
        text = html2plaintext(parsed.get('body') or '')
        references = re.findall(r'<[^>]+>', ' '.join(filter(None, [parsed.get('in_reply_to'), parsed.get('references')])))
        parent = references and Message.search([('mailbox_id', '=', self.id), ('message_id', 'in', references)], limit=1)
        key = client_key(sender)
        known_client = Message.search([('mailbox_id', '=', self.id), ('client_key', '=', key), ('kind', '=', 'rfq')], limit=1)
        if not parent and not known_client:
            if is_non_rfq(subject, text, parsed.get('email_from')) or not has_rfq_intent(subject, text):
                return False
            kind = 'rfq'
        else:
            kind = 'client'
        record = Message.create({
            'mailbox_id': self.id,
            'kind': kind,
            'message_id': message_id,
            'references': ' '.join(references),
            'parent_id': parent.id if parent else False,
            'subject': subject,
            'email_from': parsed.get('email_from'),
            'email_to': parsed.get('to'),
            'email_cc': parsed.get('cc'),
            'date': parsed.get('date') or fields.Datetime.now(),
            'body_html': parsed.get('body'),
            'client_key': key,
        })
        record._save_attachments(parsed.get('attachments') or [])
        if kind == 'rfq' and self.create_taskhub_rfq:
            record._link_taskhub_rfq(raw)
        elif kind == 'client':
            record.taskhub_rfq_id = (parent.taskhub_rfq_id if parent else False) or known_client.taskhub_rfq_id
        record._notify_owner()
        return record
