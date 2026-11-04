import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import _, fields, http
from odoo.addons.technoai_client_portal.controllers.main import (
    STAFF_REFUSED, ClientPortal, ClientPortalHome, ClientPortalMy, _is_staff_login, _signed_in_staff,
)
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools import plaintext2html

from ..models.purchase_order import CARRIERS

_logger = logging.getLogger(__name__)

PORTAL = '/supplierportal'
MAX_UPLOAD = 15 * 1024 * 1024


def _is_supplier_only(user):
    """ A portal user of a company we buy from and do not sell to. """
    company = user.partner_id.commercial_partner_id
    supplier = company.supplier_rank > 0 or company.taskhub_is_supplier
    return user.share and supplier and not company.customer_rank


class SupplierPortalHome(ClientPortalHome):

    def _login_redirect(self, uid, redirect=None):
        user = request.env['res.users'].sudo().browse(uid)
        if not redirect and _is_supplier_only(user):
            redirect = PORTAL + '/home'
        return super()._login_redirect(uid, redirect=redirect)


class SupplierPortalMy(ClientPortalMy):

    @http.route()
    def home(self, **kw):
        if request.session.uid and _is_supplier_only(request.env.user):
            return request.redirect(PORTAL + '/home')
        return super().home(**kw)


class SupplierPortal(http.Controller):
    """ /supplierportal: the supplier's RFQs, purchase orders, shipments, documents and payments. """

    # the client portal's helpers, borrowed rather than inherited: inheriting its controller would hand
    # this class's _guard to the client portal's own routes
    _company_partner = ClientPortal._company_partner
    _domain = ClientPortal._domain
    _owned = ClientPortal._owned
    _totals = ClientPortal._totals

    def _guard(self):
        if not request.session.uid or request.env.user._is_public():
            return request.redirect(PORTAL)
        if not request.env.user.share:
            # a staff session in this browser: the portal's sign-in page explains it, never the ERP
            return request.redirect(PORTAL)
        return None

    def _owned_po(self, order_id):
        return self._owned('purchase.order', order_id)

    def _purchase(self, domain):
        return request.env['purchase.order'].sudo().search(self._domain() + domain, order='date_order desc, id desc')

    def _rfqs(self):
        return self._purchase([('state', 'in', ('draft', 'sent'))])

    def _orders(self):
        return self._purchase([('state', 'in', ('purchase', 'done'))])

    def _bills(self):
        return request.env['account.move'].sudo().search(
            self._domain() + [('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'posted')], order='invoice_date desc, id desc')

    def _open_lines(self):
        """ Ordered items not received yet. """
        return self._orders().order_line.filtered(lambda l: not l.display_type and l.qty_received < l.product_qty)

    def _render(self, template, active, values):
        values.update({'carriers': CARRIERS, 'portal': PORTAL})
        return ClientPortal._render(self, template, active, values)

    # ------------------------------------------------------------------
    # Sign in
    # ------------------------------------------------------------------

    @http.route(PORTAL, type='http', auth='public', sitemap=False)
    def supplier_login_page(self, **kw):
        if request.session.uid and request.env.user.share and not request.env.user._is_public():
            return request.redirect(PORTAL + '/home')
        return request.render('technoai_supplier_portal.login', {'error': kw.get('error'), 'login': kw.get('login', ''),
                                                                  'staff': _signed_in_staff(), 'portal': PORTAL})

    @http.route(PORTAL + '/login', type='http', auth='public', methods=['POST'], sitemap=False)
    def supplier_login(self, login=None, password=None, **kw):
        if _is_staff_login(login):
            return request.render('technoai_supplier_portal.login', {'error': STAFF_REFUSED, 'login': login,
                                                                      'staff': _signed_in_staff(), 'portal': PORTAL})
        try:
            request.session.authenticate(request.db, {'login': (login or '').strip(), 'password': password or '', 'type': 'password'})
        except AccessDenied:
            return request.render('technoai_supplier_portal.login', {'error': _('Wrong email or password.'), 'login': login})
        except Exception as error:
            _logger.info('Supplier portal sign-in refused for %s: %s', login, error)
            return request.render('technoai_supplier_portal.login', {'error': str(error), 'login': login})
        if not request.env.user.share:  # cannot happen after _is_staff_login, kept as a safety net
            request.session.logout(keep_db=True)
            return request.render('technoai_supplier_portal.login', {'error': STAFF_REFUSED, 'login': login, 'portal': PORTAL})
        return request.redirect(PORTAL + '/home')

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @http.route(PORTAL + '/home', type='http', auth='public', sitemap=False)
    def supplier_home(self, **kw):
        if (redirect := self._guard()):
            return redirect
        rfqs, orders, bills = self._rfqs(), self._orders(), self._bills()
        today = fields.Date.context_today(request.env.user)
        week = today + timedelta(days=7)
        due = self._open_lines().filtered(lambda l: l.tai_ship_status != 'shipped' and l.date_planned and l.date_planned.date() <= week)
        unpaid = bills.filtered(lambda m: m.move_type == 'in_invoice' and m.payment_state in ('not_paid', 'partial'))
        payments = request.env['account.payment'].sudo().search(self._domain() + [('payment_type', '=', 'outbound'), ('state', 'in', ('paid', 'in_process'))],
                                                                 order='date desc', limit=4) if 'account.payment' in request.env else []
        return self._render('technoai_supplier_portal.home', 'home', {
            'rfqs': rfqs.filtered(lambda o: not o.tai_vendor_quoted_date)[:6],
            'rfq_count': len(rfqs.filtered(lambda o: not o.tai_vendor_quoted_date)),
            'orders': orders[:8],
            'to_accept': orders.filtered(lambda o: not o.tai_vendor_accepted_date and o.state == 'purchase'),
            'due_count': len(due),
            'unpaid': unpaid,
            'unpaid_totals': self._totals(unpaid, 'amount_residual'),
            'payments': payments,
            'today': today,
        })

    @http.route(PORTAL + '/rfqs', type='http', auth='public', sitemap=False)
    def supplier_rfqs(self, **kw):
        if (redirect := self._guard()):
            return redirect
        return self._render('technoai_supplier_portal.rfqs', 'rfqs', {'rfqs': self._rfqs()})

    @http.route(PORTAL + '/rfqs/<int:order_id>', type='http', auth='public', methods=['GET', 'POST'], sitemap=False)
    def supplier_rfq(self, order_id, **post):
        if (redirect := self._guard()):
            return redirect
        order = self._owned_po(order_id)
        if not order or order.state not in ('draft', 'sent'):
            return request.redirect(PORTAL + '/rfqs')
        error = False
        if request.httprequest.method == 'POST':
            error = self._save_prices(order, post)
            if not error:
                return request.redirect('%s/rfqs/%s?sent=1' % (PORTAL, order.id))
        return self._render('technoai_supplier_portal.rfq', 'rfqs', {'order': order, 'sent': post.get('sent'), 'error': error})

    def _save_prices(self, order, post):
        lines = order.order_line.filtered(lambda l: not l.display_type)
        for line in lines:
            cannot = bool(post.get('cannot_%s' % line.id))
            raw = (post.get('price_%s' % line.id) or '').replace(',', '').strip()
            values = {'tai_vendor_cannot_quote': cannot, 'tai_vendor_note': (post.get('note_%s' % line.id) or '').strip()[:250]}
            if not cannot:
                try:
                    price = float(raw) if raw else 0.0
                except ValueError:
                    return _('The price of "%s" is not a number.', line.name.split('\n')[0])
                if price < 0:
                    return _('Prices cannot be negative.')
                values['price_unit'] = price
            days = (post.get('lead_%s' % line.id) or '').strip()
            if days.isdigit():
                values['tai_vendor_lead_days'] = int(days)
                values['date_planned'] = fields.Datetime.now() + timedelta(days=int(days))
            line.write(values)
        order.write({'tai_vendor_quoted_date': fields.Datetime.now()})
        self._attach(order, _('Quotation from the supplier'))
        order._tai_index_vendor_prices()
        rows = Markup('<br/>').join(
            Markup('%s: %s') % (l.name.split('\n')[0], _("can't quote") if l.tai_vendor_cannot_quote else '%s %s' % (order.currency_id.name, '{:,.2f}'.format(l.price_unit)))
            for l in lines)
        order._tai_notify_buyer(_('%(supplier)s sent prices for %(rfq)s', supplier=order._tai_vendor_partner().name, rfq=order.name),
                                Markup('<p><b>%s</b></p><p>%s</p>') % (_('Prices sent in the supplier portal'), rows))
        return False

    def _attach(self, order, label):
        names = []
        for upload in request.httprequest.files.getlist('attachments'):
            content = upload.read(MAX_UPLOAD + 1)
            if content and len(content) <= MAX_UPLOAD:
                request.env['ir.attachment'].sudo().create({'name': upload.filename, 'raw': content, 'res_model': order._name, 'res_id': order.id})
                names.append(upload.filename)
        if names:
            order._tai_notify_buyer(_('%(supplier)s uploaded documents on %(po)s', supplier=order._tai_vendor_partner().name, po=order.name),
                                    Markup('<p>%s: %s</p>') % (label, ', '.join(names)))
        return names

    @http.route(PORTAL + '/orders', type='http', auth='public', sitemap=False)
    def supplier_orders(self, **kw):
        if (redirect := self._guard()):
            return redirect
        return self._render('technoai_supplier_portal.orders', 'orders', {'orders': self._orders()})

    @http.route(PORTAL + '/orders/<int:order_id>', type='http', auth='public', sitemap=False)
    def supplier_order(self, order_id, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned_po(order_id)
        if not order or order.state not in ('purchase', 'done'):
            return request.redirect(PORTAL + '/orders')
        messages = order.message_ids.filtered(
            lambda m: m.message_type in ('comment', 'email') and m.subtype_id and not m.subtype_id.internal).sorted('date')
        attachments = request.env['ir.attachment'].sudo().search([('res_model', '=', 'purchase.order'), ('res_id', '=', order.id)])
        return self._render('technoai_supplier_portal.order', 'orders', {
            'order': order, 'messages': messages, 'attachments': attachments,
            'bills': order.invoice_ids.filtered(lambda m: m.state == 'posted'),
            'saved': kw.get('saved'), 'sent': kw.get('sent'), 'uploaded': kw.get('uploaded'),
        })

    @http.route(PORTAL + '/orders/<int:order_id>/accept', type='http', auth='public', methods=['POST'], sitemap=False)
    def supplier_accept(self, order_id, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned_po(order_id)
        if order and order.state == 'purchase' and not order.tai_vendor_accepted_date:
            order.tai_vendor_accepted_date = fields.Datetime.now()
            order._tai_notify_buyer(_('%(supplier)s accepted %(po)s', supplier=order._tai_vendor_partner().name, po=order.name),
                                    Markup('<p>%s</p>') % _('The supplier accepted the purchase order in the supplier portal.'))
        return request.redirect('%s/orders/%s' % (PORTAL, order_id))

    @http.route(PORTAL + '/orders/<int:order_id>/shipment', type='http', auth='public', methods=['POST'], sitemap=False)
    def supplier_shipment(self, order_id, **post):
        if (redirect := self._guard()):
            return redirect
        order = self._owned_po(order_id)
        if not order or order.state != 'purchase':
            return request.redirect(PORTAL + '/orders')
        carriers = dict(CARRIERS)
        changed = request.env['purchase.order.line'].sudo()
        for line in order.order_line.filtered(lambda l: not l.display_type):
            status = post.get('status_%s' % line.id) or False
            if status not in (False, 'ready', 'shipped'):
                continue
            date = post.get('date_%s' % line.id)
            carrier = post.get('carrier_%s' % line.id) or False
            values = {
                'tai_ship_status': status,
                'tai_ship_date': fields.Date.to_date(date) if date else False,
                'tai_carrier': carrier if carrier in carriers else False,
                'tai_tracking_ref': (post.get('ref_%s' % line.id) or '').strip()[:300],
            }
            if any(line[key] != value for key, value in values.items()):
                line.write(values)
                changed |= line
        if changed:
            if not order.tai_vendor_accepted_date:
                order.tai_vendor_accepted_date = fields.Datetime.now()
            changed._tai_apply_shipment()
            order._tai_notify_buyer(_('%(supplier)s updated the shipment of %(po)s', supplier=order._tai_vendor_partner().name, po=order.name),
                                    Markup('<p>%s</p>') % Markup('<br/>').join(line._tai_shipment_summary() for line in changed))
        return request.redirect('%s/orders/%s?saved=1' % (PORTAL, order_id))

    @http.route(PORTAL + '/orders/<int:order_id>/upload', type='http', auth='public', methods=['POST'], sitemap=False)
    def supplier_upload(self, order_id, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned_po(order_id)
        if order:
            self._attach(order, _('Documents from the supplier'))
        return request.redirect('%s/orders/%s?uploaded=1' % (PORTAL, order_id))

    @http.route(PORTAL + '/orders/<int:order_id>/message', type='http', auth='public', methods=['POST'], sitemap=False)
    def supplier_message(self, order_id, message=None, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned_po(order_id)
        text = (message or '').strip()
        if order and text:
            order.message_post(body=plaintext2html(text[:4000]), author_id=request.env.user.partner_id.id,
                               message_type='comment', subtype_xmlid='mail.mt_comment')
            if order.user_id:
                order.message_subscribe(partner_ids=order.user_id.partner_id.ids)
        return request.redirect('%s/orders/%s?sent=1#messages' % (PORTAL, order_id))

    @http.route(PORTAL + '/shipments', type='http', auth='public', sitemap=False)
    def supplier_shipments(self, **kw):
        if (redirect := self._guard()):
            return redirect
        return self._render('technoai_supplier_portal.shipments', 'shipments', {
            'lines': self._open_lines().sorted(lambda l: l.date_planned or fields.Datetime.now()),
            'today': fields.Date.context_today(request.env.user),
        })

    @http.route(PORTAL + '/payments', type='http', auth='public', sitemap=False)
    def supplier_payments(self, **kw):
        if (redirect := self._guard()):
            return redirect
        bills = self._bills()
        unpaid = bills.filtered(lambda m: m.move_type == 'in_invoice' and m.payment_state in ('not_paid', 'partial'))
        return self._render('technoai_supplier_portal.payments', 'payments', {
            'bills': bills, 'unpaid_totals': self._totals(unpaid, 'amount_residual'),
            'today': fields.Date.context_today(request.env.user),
        })

    @http.route(PORTAL + '/pdf/<int:order_id>', type='http', auth='public', sitemap=False)
    def supplier_pdf(self, order_id, **kw):
        if (redirect := self._guard()):
            return redirect
        order = self._owned_po(order_id)
        if not order:
            return request.not_found()
        report = 'purchase.report_purchase_quotation' if order.state in ('draft', 'sent') else 'purchase.action_report_purchase_order'
        pdf, _type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report, order.ids)
        return request.make_response(pdf, headers=[('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)),
                                                   ('Content-Disposition', 'attachment; filename="%s.pdf"' % order.name)])

    @http.route(PORTAL + '/attachment/<int:attachment_id>', type='http', auth='public', sitemap=False)
    def supplier_attachment(self, attachment_id, **kw):
        if (redirect := self._guard()):
            return redirect
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != 'purchase.order' or not self._owned_po(attachment.res_id):
            return request.not_found()
        return request.make_response(attachment.raw, headers=[('Content-Type', attachment.mimetype or 'application/octet-stream'),
                                                              ('Content-Disposition', 'attachment; filename="%s"' % attachment.name)])
