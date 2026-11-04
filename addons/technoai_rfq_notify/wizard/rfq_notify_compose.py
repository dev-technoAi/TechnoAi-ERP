import base64
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, make_msgid

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize, html2plaintext

_logger = logging.getLogger(__name__)


class RfqNotifyCompose(models.TransientModel):
    """ Reply, reply all or forward from the employee's own mailbox, with their own signature. """
    _name = 'rfq.notify.compose'
    _description = 'Write an email from my mailbox'

    message_id = fields.Many2one('rfq.notify.message', required=True, ondelete='cascade')
    mode = fields.Selection([('reply', 'Reply'), ('reply_all', 'Reply all'), ('forward', 'Forward')], default='reply', required=True)
    mailbox_id = fields.Many2one(related='message_id.mailbox_id')
    email_from = fields.Char('From', compute='_compute_email_from')
    email_to = fields.Char('To', required=True)
    email_cc = fields.Char('Cc')
    subject = fields.Char(required=True)
    body = fields.Html(sanitize_style=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    quotation_id = fields.Many2one('taskhub.quotation', 'Draft Quotation', compute='_compute_quotation_id')

    @api.depends('mailbox_id')
    def _compute_email_from(self):
        for wizard in self:
            wizard.email_from = formataddr((wizard.mailbox_id.user_id.name or '', wizard.mailbox_id.email or ''))

    @api.depends('message_id')
    def _compute_quotation_id(self):
        for wizard in self:
            wizard.quotation_id = wizard.message_id.taskhub_quotation_id

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        source = self.env['rfq.notify.message'].browse(values.get('message_id') or self.env.context.get('default_message_id'))
        if not source:
            return values
        mode = values.get('mode') or 'reply'
        own = email_normalize(source.mailbox_id.email)
        subject = source.subject or ''
        prefix = 'Fwd: ' if mode == 'forward' else 'Re: '
        if not subject.lower().startswith(prefix.lower()):
            subject = prefix + subject
        values['subject'] = subject
        if mode != 'forward':
            values['email_to'] = source.email_from
        if mode == 'reply_all':
            others = [formataddr((name, address)) for name, address in getaddresses([source.email_to or '', source.email_cc or ''])
                      if address and email_normalize(address) not in (own, email_normalize(source.email_from))]
            values['email_cc'] = ', '.join(others)
        signature = source.mailbox_id.signature or ''
        values['body'] = Markup('<p><br/></p><div class="o_rfqn_signature">%s</div>%s') % (Markup(signature), source._quote_html())
        if mode == 'forward' and source.attachment_ids:
            values['attachment_ids'] = [(6, 0, source.attachment_ids.ids)]
        return values

    def action_attach_quotation(self):
        """ Add the PDF of the RFQ's latest Draft Quotation. """
        self.ensure_one()
        if not self.quotation_id:
            raise UserError(_('This RFQ has no Draft Quotation yet. Open it from Task Hub first.'))
        pdf, _type = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'technoai_taskhub.action_report_taskhub_quotation', self.quotation_id.ids)
        attachment = self.env['ir.attachment'].create({
            'name': '%s.pdf' % self.quotation_id.name,
            'datas': base64.b64encode(pdf),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.attachment_ids = [(4, attachment.id)]
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
                'name': _('Write email')}

    def _build_email(self):
        self.ensure_one()
        source = self.message_id
        mailbox = source.mailbox_id
        message = EmailMessage()
        message['From'] = self.email_from
        message['To'] = self.email_to
        if self.email_cc:
            message['Cc'] = self.email_cc
        message['Subject'] = self.subject
        domain = (mailbox.email or 'technoai.ae').rpartition('@')[2]
        message['Message-ID'] = make_msgid(domain=domain)
        if self.mode != 'forward' and source.message_id:
            message['In-Reply-To'] = source.message_id
            message['References'] = ' '.join(filter(None, [source.references, source.message_id]))
        html = self.body or ''
        message.set_content(html2plaintext(html))
        message.add_alternative(str(html), subtype='html')
        for attachment in self.attachment_ids:
            maintype, _slash, subtype = (attachment.mimetype or 'application/octet-stream').partition('/')
            message.add_attachment(attachment.raw, maintype=maintype, subtype=subtype or 'octet-stream', filename=attachment.name)
        return message

    def action_send(self):
        self.ensure_one()
        source = self.message_id
        mailbox = source.mailbox_id.sudo()
        if mailbox.user_id != self.env.user and not self.env.user.has_group('technoai_rfq_notify.group_rfq_notify_manager'):
            raise UserError(_('Only the owner of %s can send from it.', mailbox.email))
        message = self._build_email()
        recipients = [address for _name, address in getaddresses([self.email_to or '', self.email_cc or '']) if address]
        try:
            smtp = mailbox._smtp()
            try:
                smtp.send_message(message, from_addr=mailbox.email, to_addrs=recipients)
            finally:
                smtp.quit()
        except (OSError, smtplib.SMTPException) as error:
            raise UserError(_('%(mailbox)s could not send the email: %(error)s', mailbox=mailbox.email, error=error)) from error
        sent = self.env['rfq.notify.message'].sudo().create({
            'mailbox_id': mailbox.id,
            'kind': 'sent',
            'message_id': message['Message-ID'],
            'references': message.get('References'),
            'parent_id': source.id if self.mode != 'forward' else False,
            'subject': self.subject,
            'email_from': self.email_from,
            'email_to': self.email_to,
            'email_cc': self.email_cc,
            'body_html': self.body,
            'client_key': source.client_key,
            'taskhub_rfq_id': source.taskhub_rfq_id.id,
            'opened_date': fields.Datetime.now(),
        })
        if self.attachment_ids:
            sent.attachment_ids = self.attachment_ids.sudo().copy({'res_model': sent._name, 'res_id': sent.id})
        if source.taskhub_rfq_id:
            source.taskhub_rfq_id.sudo().message_post(
                body=Markup('%s<br/>%s') % (_('Email sent from %s:', mailbox.email), self.subject), subtype_xmlid='mail.mt_note')
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'title': _('Email sent'), 'message': _('Sent from %s.', mailbox.email),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
