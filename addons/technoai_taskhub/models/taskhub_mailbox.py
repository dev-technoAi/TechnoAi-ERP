import email
import email.policy
import imaplib
import logging
import re

from odoo import _, api, models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

# the filters of the original Task Hub (shared/rfq.ts and email-fetcher.ts)
NON_RFQ_SENDER = re.compile(
    r'(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|donot[-_.]?reply|mailer[-_.]?daemon|postmaster|bounce|newsletters?|'
    r'marketing|promotions?|campaigns?|alerts?@|digest@|updates?@|announcements?@)', re.I)
NON_RFQ_PLATFORM = re.compile(
    r'@.*(?:binance|coinbase|kucoin|bybit|okx|kraken|bitfinex|crypto|linkedin|facebookmail|twitter|x\.com|tiktok|'
    r'pinterest|instagram|medium\.com|substack|quora|redditmail|netflix|spotify|uber|careem|smailer\d*)\.com', re.I)
NON_RFQ_SUBJECT = re.compile(
    r'(?:halloween|pumpkin|surprise\?|referral|voucher|token\s+voucher|usdc|usdt|crypto|bitcoin|airdrop|lucky\s+draw|'
    r'cashback|spin\s+the\s+wheel|open\s+it\s+with\s+a\s+friend|giveaway|bonus\s+prize|winner|congratulations|'
    r'black\s+friday|cyber\s+monday|sale\s+is\s+live|special\s+discount|limited\s+time\s+offer|newsletter|'
    r'weekly\s+digest|account\s+statement|receipt\s+for|order\s+confirmation|shipping\s+update|tracking\s+number|'
    r'password\s+reset|verify\s+your\s+email|security\s+alert|sign-in\s+attempt|otp\b|one-time\s+password)', re.I)
NON_RFQ_BODY = re.compile(
    r'(?:join\s+the\s+campaign|referral\s+pro\s+link|token\s+voucher\s+worth|earn\s+one\s+pumpkin|'
    r'qualifying\s+friend|eligibility\s+checks|unsubscribe\s+from\s+this\s+list|click\s+here\s+to\s+unsubscribe|'
    r'manage\s+your\s+preferences|view\s+in\s+browser)', re.I)
RFQ_SUBJECT = re.compile(
    r'(?:rfq|rffq|rfp|request for quotation|request for quote|quotation request|quote request|pricing inquiry|'
    r'price inquiry|price request|material inquiry|inquiry for|enquiry for|tender|boq|bill of quantities|'
    r'procurement of|supply of|purchase of|quote required)', re.I)
RFQ_BODY = re.compile(
    r'(?:please\s+(?:provide|send|quote|share)|kindly\s+(?:provide|send|quote|share)|'
    r'request(?:ing)?\s+(?:for\s+)?quotation|request\s+for\s+quote|we\s+(?:require|need|are\s+looking\s+for)|'
    r'quote\s+for\s+the\s+following|rfq\s+for|inquiry\s+for|commercial proposal|price proposal|material request|swmsei)', re.I)
RFQ_REFERENCE = re.compile(r'(?:rfq|rffq|rfp)[-_\s]?[a-z0-9]+', re.I)
SUBJECT_SEARCH = ['RFQ', 'Quote', 'Quotation', 'rffq']


def is_non_rfq(subject, body, sender):
    sender = (sender or '').lower()
    return bool(NON_RFQ_SENDER.search(sender) or NON_RFQ_PLATFORM.search(sender)
                or NON_RFQ_SUBJECT.search(subject or '') or NON_RFQ_BODY.search('%s %s' % (subject, body)))


def has_rfq_intent(subject, body):
    return bool(RFQ_SUBJECT.search(subject or '') or RFQ_BODY.search(body or '')
                or RFQ_REFERENCE.search('%s %s' % (subject, body)))


class TaskhubMailbox(models.AbstractModel):
    """ Reads RFQ emails from a shared mailbox the way the original Task Hub did:
    the mailbox is opened read-only (nothing is marked as read or moved), only
    emails that look like quotation requests become Email RFQs, and an email is
    never imported twice. """
    _name = 'taskhub.mailbox'
    _description = 'Task Hub RFQ mailbox'

    @api.model
    def _settings(self):
        params = self.env['ir.config_parameter'].sudo()
        return {
            'enabled': params.get_param('technoai_taskhub.rfq_mailbox') == 'True',
            'host': params.get_param('technoai_taskhub.imap_host') or 'imap.gmail.com',
            'port': int(params.get_param('technoai_taskhub.imap_port') or 993),
            'user': (params.get_param('technoai_taskhub.imap_user') or '').strip(),
            'password': params.get_param('technoai_taskhub.imap_password') or '',
        }

    @api.model
    def is_configured(self):
        settings = self._settings()
        return bool(settings['enabled'] and settings['user'] and settings['password'])

    @api.model
    def _connect(self, settings):
        if settings['port'] == 993:
            imap = imaplib.IMAP4_SSL(settings['host'], settings['port'], timeout=15)
        else:
            imap = imaplib.IMAP4(settings['host'], settings['port'], timeout=15)
            imap.starttls()
        password = settings['password']
        if 'gmail' in settings['host'].lower():
            password = re.sub(r'\s+', '', password)  # app passwords are shown with spaces
        imap.login(settings['user'], password)
        return imap

    @api.model
    def _candidate_uids(self, imap, limit):
        """ Newest emails, unread emails and emails with RFQ words in the subject, newest first. """
        uids = set()
        _status, data = imap.uid('search', None, 'ALL')
        uids.update(data[0].split()[-max(limit * 2, 40):])
        _status, data = imap.uid('search', None, 'UNSEEN')
        uids.update(data[0].split())
        for word in SUBJECT_SEARCH:
            _status, data = imap.uid('search', None, 'SUBJECT', '"%s"' % word)
            uids.update(data[0].split()[-limit:])
        return sorted(uids, key=int)[-limit:][::-1]

    @api.model
    def fetch_rfq_emails(self, limit=15):
        """ Import new RFQ emails; returns counters for the caller. """
        settings = self._settings()
        if not self.is_configured():
            return {'configured': False}
        result = {'configured': True, 'created': 0, 'skipped': 0, 'known': 0}
        imap = self._connect(settings)
        try:
            imap.select('INBOX', readonly=True)  # read-only: the mailbox stays exactly as it is
            MailThread = self.env['mail.thread']
            for uid in self._candidate_uids(imap, limit):
                _status, data = imap.uid('fetch', uid, '(BODY.PEEK[])')
                raw = next((part[1] for part in data if isinstance(part, tuple)), None)
                if not raw:
                    continue
                message = email.message_from_bytes(raw, policy=email.policy.SMTP)
                parsed = MailThread.message_parse(message)
                message_id = parsed.get('message_id')
                if message_id and self.env['mail.message'].sudo().search_count([('message_id', '=', message_id)]):
                    result['known'] += 1
                    continue
                subject = parsed.get('subject') or ''
                body = html2plaintext(parsed.get('body') or '')
                # replies to emails sent from Techno AI go to their document whatever they say
                references = re.findall(r'<[^>]+>', ' '.join(filter(None, [parsed.get('in_reply_to'), parsed.get('references')])))
                is_reply = bool(references) and bool(self.env['mail.message'].sudo().search_count([('message_id', 'in', references)]))
                if not is_reply and (is_non_rfq(subject, body, parsed.get('email_from')) or not has_rfq_intent(subject, body)):
                    result['skipped'] += 1
                    continue
                try:
                    with self.env.cr.savepoint():
                        MailThread.sudo().message_process('taskhub.rfq', raw, save_original=False)
                    result['created'] += 1
                except Exception:
                    _logger.exception('Task Hub could not import RFQ email %s', message_id)
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        return result

    @api.model
    def _cron_fetch_rfq_emails(self):
        if not self.is_configured():
            return
        try:
            result = self.fetch_rfq_emails()
            if result.get('created'):
                _logger.info('Task Hub imported %s RFQ email(s)', result['created'])
        except (OSError, imaplib.IMAP4.error) as error:
            _logger.warning('Task Hub RFQ mailbox could not be read: %s', error)
