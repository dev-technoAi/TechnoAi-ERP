from odoo import http
from odoo.http import request
from odoo.tools import email_normalize


class TrackingPublic(http.Controller):
    """ The client's tracking page: only the PO number, items, public status, ETA and shipment link. """

    def _find(self, po):
        po = (po or '').strip()
        if not po:
            return request.env['technoai.tracking.order'].sudo().browse()
        return request.env['technoai.tracking.order'].sudo().search([('name', '=ilike', po)], limit=1)

    @http.route('/track', type='http', auth='public', sitemap=False)
    def track(self, po=None, **kw):
        order = self._find(po)
        return request.render('technoai_tracking.public_track', {
            'po': (po or '').strip(),
            'order': order,
            'searched': bool(po),
            'message': kw.get('message'),
        })

    @http.route('/track/subscribe', type='http', auth='public', methods=['POST'], sitemap=False)
    def subscribe(self, po=None, email=None, **kw):
        order = self._find(po)
        email = email_normalize(email or '')
        if not order or not email:
            return request.redirect('/track?po=%s&message=invalid' % (po or ''))
        Subscriber = request.env['technoai.tracking.subscriber'].sudo()
        subscriber = Subscriber.search([('order_id', '=', order.id), ('email', '=', email)], limit=1)
        if not subscriber:
            subscriber = Subscriber.create({'order_id': order.id, 'email': email})
        if not subscriber.confirmed:
            subscriber._send_confirmation()
        return request.redirect('/track?po=%s&message=%s' % (order.name, 'confirmed' if subscriber.confirmed else 'check'))

    @http.route('/track/confirm/<string:token>', type='http', auth='public', sitemap=False)
    def confirm(self, token, **kw):
        subscriber = request.env['technoai.tracking.subscriber'].sudo().search([('token', '=', token)], limit=1)
        if not subscriber:
            return request.redirect('/track?message=invalid')
        subscriber.confirmed = True
        return request.redirect('/track?po=%s&message=subscribed' % subscriber.order_id.name)

    @http.route('/track/unsubscribe/<string:token>', type='http', auth='public', sitemap=False)
    def unsubscribe(self, token, **kw):
        subscriber = request.env['technoai.tracking.subscriber'].sudo().search([('token', '=', token)], limit=1)
        po = subscriber.order_id.name
        subscriber.unlink()
        return request.redirect('/track?po=%s&message=unsubscribed' % (po or ''))
