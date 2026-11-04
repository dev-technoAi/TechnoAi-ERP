import logging
from collections import OrderedDict

from markupsafe import Markup

from odoo import _, fields, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.web import Home
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)

PORTAL = '/clientportal'
REPORTS = {
    'sale.order': 'sale.action_report_saleorder',
    'account.move': 'account.account_invoices',
    'stock.picking': 'stock.action_report_delivery',
}
MAX_UPLOAD = 15 * 1024 * 1024


def _is_client():
    user = request.env.user
    return bool(request.session.uid) and user.share and not user._is_public()


class ClientPortalHome(Home):
    """ Clients land on the client portal instead of Odoo's /my. """

    def _login_redirect(self, uid, redirect=None):
        if not redirect and not request.env['res.users'].sudo().browse(uid)._is_internal():
            redirect = PORTAL + '/home'
        return super()._login_redirect(uid, redirect=redirect)


class ClientPortalMy(CustomerPortal):

    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def home(self, **kw):
        if _is_client():
            return request.redirect(PORTAL + '/home')
        return super().home(**kw)


class ClientPortal(http.Controller):

    # ------------------------------------------------------------------
    # Helpers: everything is read for the client's own company only
    # ------------------------------------------------------------------

    def _company_partner(self):
        return request.env.user.partner_id.commercial_partner_id

    def _domain(self, field='partner_id'):
        return [(field, 'child_of', self._company_partner().id)]

    def _guard(self):
        """ None when a client is signed in, else where to send the visitor. """
        if not request.session.uid or request.env.user._is_public():
            return request.redirect(PORTAL)
        if not request.env.user.share:
            return request.redirect('/odoo')
        return None

    def _owned(self, model, record_id):
        record = request.env[model].sudo().browse(int(record_id)).exists()
        field = 'partner_id'
        if record and record[field].commercial_partner_id == self._company_partner():
            return record
        return request.env[model].sudo().browse()

    def _totals(self, records, amount_field):
        """ {currency: total}, never mixing currencies, with the AED value when a rate exists. """
        company = request.env.company
        totals = OrderedDict()
        for record in records:
            totals.setdefault(record.currency_id, 0.0)
            totals[record.currency_id] += record[amount_field]
        rated = set(request.env['res.currency.rate'].sudo().search([('currency_id', 'in', [c.id for c in totals])]).currency_id.ids)
        result = []
        for currency, amount in totals.items():
            local = False
            if currency != company.currency_id and currency.id in rated:
                local = currency._convert(amount, company.currency_id, company, fields.Date.context_today(request.env.user))
            result.append({'currency': currency, 'amount': amount, 'local': local})
        return result

    def _render(self, template, active, values):
        values.update({
            'active': active,
            'client': request.env.user.partner_id,
            'company_partner': self._company_partner(),
            'manager': self._company_partner().user_id,
            'money': lambda amount, currency: '%s %s' % (currency.name, '{:,.{}f}'.format(amount, currency.decimal_places)) if currency else '{:,.2f}'.format(amount),
            'fmt_date': lambda value: value.strftime('%d %b %Y') if value else '-',
            'company_currency': request.env.company.currency_id,
        })
        return request.render(template, values)

    def _quotations(self):
        return request.env['sale.order'].sudo().search(self._domain() + [('state', 'in', ('draft', 'sent'))], order='date_order desc')

    def _orders(self):
        return request.env['sale.order'].sudo().search(self._domain() + [('state', '=', 'sale')], order='date_order desc')

    def _invoices(self):
        return request.env['account.move'].sudo().search(
            self._domain() + [('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted')], order='invoice_date desc, id desc')

    def _deliveries(self):
        return request.env['stock.picking'].sudo().search(
            self._domain() + [('picking_type_code', '=', 'outgoing'), ('state', '!=', 'cancel')], order='scheduled_date desc')

    # ------------------------------------------------------------------
    # Sign in
    # ------------------------------------------------------------------

    @http.route(PORTAL, type='http', auth='public', sitemap=False)
    def login_page(self, **kw):
        if _is_client():
            return request.redirect(PORTAL + '/home')
        return request.render('technoai_client_portal.login', {'error': kw.get('error'), 'login': kw.get('login', '')})

    @http.route(PORTAL + '/login', type='http', auth='public', methods=['POST'], sitemap=False)
    def login(self, login=None, password=None, **kw):
        try:
            request.session.authenticate(request.db, {'login': (login or '').strip(), 'password': password or '', 'type': 'password'})
        except AccessDenied:
            return request.render('technoai_client_portal.login', {'error': _('Wrong email or password.'), 'login': login})
        except Exception as error:  # e.g. too many attempts
            _logger.info('Client portal sign-in refused for %s: %s', login, error)
            return request.render('technoai_client_portal.login', {'error': str(error), 'login': login})
        if not request.env.user.share:
            return request.redirect('/odoo')
        return request.redirect(PORTAL + '/home')

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @http.route(PORTAL + '/home', type='http', auth='user', sitemap=False)
    def home(self, **kw):
        if (redirect := self._guard()):
            return redirect
        quotations, orders, invoices = self._quotations(), self._orders(), self._invoices()
        to_pay = invoices.filtered(lambda m: m.move_type == 'out_invoice' and m.payment_state in ('not_paid', 'partial'))
        today = fields.Date.context_today(request.env.user)
        tracking = orders.tracking_ids
        updates = tracking.line_ids.sorted('last_update', reverse=True)[:6]
        return self._render('technoai_client_portal.home', 'home', {
            'quotations': quotations[:5],
            'quotation_count': len(quotations),
            'open_orders': orders.filtered(lambda o: not o.tracking_ids or o.tracking_ids[:1].state == 'open'),
            'items_on_way': len(tracking.filtered(lambda t: t.state == 'open').line_ids.filtered(lambda l: l.status != 'delivered')),
            'to_pay': to_pay,
            'to_pay_totals': self._totals(to_pay, 'amount_residual'),
            'overdue_count': len(to_pay.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today)),
            'today': today,
            'updates': updates,
        })

    @http.route(PORTAL + '/quotations', type='http', auth='user', sitemap=False)
    def quotations(self, **kw):
        if (redirect := self._guard()):
            return redirect
        return self._render('technoai_client_portal.quotations', 'quotations', {'quotations': self._quotations()})

    @http.route(PORTAL + '/quotations/<int:order_id>/review', type='http', auth='user', sitemap=False)
    def review(self, order_id, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned('sale.order', order_id)
        if not order:
            return request.redirect(PORTAL + '/quotations')
        # Odoo's own quotation page: accept with signature (and payment when asked)
        return request.redirect(order.get_portal_url())

    @http.route(PORTAL + '/orders', type='http', auth='user', sitemap=False)
    def orders(self, **kw):
        if (redirect := self._guard()):
            return redirect
        return self._render('technoai_client_portal.orders', 'orders', {'orders': self._orders()})

    @http.route(PORTAL + '/orders/<int:order_id>', type='http', auth='user', sitemap=False)
    def order(self, order_id, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned('sale.order', order_id)
        if not order:
            return request.redirect(PORTAL + '/orders')
        messages = order.message_ids.filtered(
            lambda m: m.message_type in ('comment', 'email') and m.subtype_id and not m.subtype_id.internal).sorted('date')
        return self._render('technoai_client_portal.order', 'orders', {
            'order': order,
            'tracking': order.tracking_ids[:1],
            'deliveries': order.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel'),
            'invoices': order.invoice_ids.filtered(lambda m: m.state == 'posted'),
            'messages': messages,
            'sent': kw.get('sent'),
        })

    @http.route(PORTAL + '/orders/<int:order_id>/message', type='http', auth='user', methods=['POST'], sitemap=False)
    def order_message(self, order_id, message=None, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned('sale.order', order_id)
        text = (message or '').strip()
        if order and text:
            order.message_post(body=plaintext2html(text[:4000]), author_id=request.env.user.partner_id.id,
                               message_type='comment', subtype_xmlid='mail.mt_comment')
            if order.user_id:
                order.message_subscribe(partner_ids=order.user_id.partner_id.ids)
        return request.redirect('%s/orders/%s?sent=1#messages' % (PORTAL, order_id))

    @http.route(PORTAL + '/deliveries', type='http', auth='user', sitemap=False)
    def deliveries(self, **kw):
        if (redirect := self._guard()):
            return redirect
        return self._render('technoai_client_portal.deliveries', 'deliveries', {'deliveries': self._deliveries()})

    @http.route(PORTAL + '/invoices', type='http', auth='user', sitemap=False)
    def invoices(self, **kw):
        if (redirect := self._guard()):
            return redirect
        invoices = self._invoices()
        today = fields.Date.context_today(request.env.user)
        open_invoices = invoices.filtered(lambda m: m.move_type == 'out_invoice' and m.payment_state in ('not_paid', 'partial'))
        year_start = today.replace(month=1, day=1)
        paid = invoices.filtered(lambda m: m.move_type == 'out_invoice' and m.payment_state in ('paid', 'in_payment')
                                 and m.invoice_date and m.invoice_date >= year_start)
        return self._render('technoai_client_portal.invoices', 'invoices', {
            'invoices': invoices,
            'today': today,
            'to_pay_totals': self._totals(open_invoices, 'amount_residual'),
            'overdue_totals': self._totals(open_invoices.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today), 'amount_residual'),
            'paid_totals': self._totals(paid, 'amount_total'),
        })

    @http.route(PORTAL + '/statement', type='http', auth='user', sitemap=False)
    def statement(self, **kw):
        if (redirect := self._guard()):
            return redirect
        invoices = self._invoices().sorted(lambda m: (m.invoice_date or fields.Date.today(), m.id))
        return self._render('technoai_client_portal.statement', 'invoices', {
            'invoices': invoices,
            'today': fields.Date.context_today(request.env.user),
            'balance_totals': self._totals(invoices.filtered(lambda m: m.payment_state in ('not_paid', 'partial')), 'amount_residual'),
        })

    @http.route(PORTAL + '/pdf/<string:kind>/<int:record_id>', type='http', auth='user', sitemap=False)
    def pdf(self, kind, record_id, **kw):
        if (redirect := self._guard()):
            return redirect
        model = {'order': 'sale.order', 'invoice': 'account.move', 'delivery': 'stock.picking'}.get(kind)
        record = model and self._owned(model, record_id)
        if not record:
            return request.not_found()
        pdf, _type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(REPORTS[model], record.ids)
        name = '%s.pdf' % (record.name or kind).replace('/', '-')
        return request.make_response(pdf, headers=[('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)),
                                                   ('Content-Disposition', 'attachment; filename="%s"' % name)])

    @http.route(PORTAL + '/request', type='http', auth='user', methods=['GET', 'POST'], sitemap=False)
    def request_quote(self, subject=None, details=None, **kw):
        if (redirect := self._guard()):
            return redirect
        if request.httprequest.method != 'POST':
            return self._render('technoai_client_portal.request', 'request', {'done': kw.get('done')})
        subject, details = (subject or '').strip(), (details or '').strip()
        if not subject:
            return self._render('technoai_client_portal.request', 'request', {'error': _('Write what you need in the title.')})
        client = request.env.user.partner_id
        company = self._company_partner()
        Rfq = request.env['taskhub.rfq'].sudo()
        rfq = Rfq.create({
            'subject': subject[:250],
            'partner_id': company.id,
            'client_name': company.name,
            'client_email': client.email,
            'email_body': Markup('<p><b>%s</b> (%s)</p>%s') % (client.name, client.email or '', plaintext2html(details[:20000])),
            'source': 'portal',
            'user_id': company.user_id.id or False,
            'line_ids': [(0, 0, item) for item in Rfq._parse_items(details)],
        })
        for upload in request.httprequest.files.getlist('attachments'):
            content = upload.read(MAX_UPLOAD + 1)
            if content and len(content) <= MAX_UPLOAD:
                request.env['ir.attachment'].sudo().create({'name': upload.filename, 'raw': content, 'res_model': rfq._name, 'res_id': rfq.id})
        rfq.message_post(body=_('Sent from the client portal by %s.', client.name), subtype_xmlid='mail.mt_note')
        if rfq.user_id:
            rfq.with_context(mail_notify_author=True).message_notify(
                author_id=request.env.ref('base.partner_root').id, partner_ids=rfq.user_id.partner_id.ids,
                subject=_('New RFQ from the client portal: %s', subject), body=Markup('<p>%s</p>') % _('%(client)s sent: %(subject)s', client=company.name, subject=subject),
                subtype_xmlid='mail.mt_comment', email_layout_xmlid='mail.mail_notification_light')
        return request.redirect(PORTAL + '/request?done=%s' % rfq.name)
