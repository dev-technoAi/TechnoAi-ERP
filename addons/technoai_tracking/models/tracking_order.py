import secrets
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize

from .tracking_line import PUBLIC_LABELS, STATUSES


class TrackingOrder(models.Model):
    """ A client order followed item by item; made from the confirmed Sales Order. """
    _name = 'technoai.tracking.order'
    _description = 'Tracked order'
    _inherit = ['mail.thread']
    _order = 'state, po_date desc, id desc'

    name = fields.Char('Client PO', required=True, tracking=True, index=True,
                       help="The client's PO number: what the client types on the tracking page.")
    sale_order_id = fields.Many2one('sale.order', 'Sales Order', ondelete='set null', index=True, copy=False)
    partner_id = fields.Many2one('res.partner', 'Client', required=True)
    contact_name = fields.Char('Contact person')
    contact_email = fields.Char('Contact email')
    user_id = fields.Many2one('res.users', 'Sales person', default=lambda self: self.env.user, tracking=True)
    payment_terms = fields.Char()
    po_date = fields.Date('PO date', default=fields.Date.context_today)
    eta_override = fields.Date('Overall ETA (set by hand)', tracking=True)
    overall_eta = fields.Date('Overall ETA', compute='_compute_progress', store=True)
    subject = fields.Char()
    internal_notes = fields.Html('Internal notes')
    state = fields.Selection([('open', 'Open'), ('closed', 'Closed')], default='open', tracking=True, index=True)
    closed_date = fields.Date('Closed on', readonly=True)
    line_ids = fields.One2many('technoai.tracking.line', 'order_id', 'Items', copy=True)
    subscriber_ids = fields.One2many('technoai.tracking.subscriber', 'order_id', 'Client subscribers')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='sale_order_id.currency_id')
    line_count = fields.Integer('Item count', compute='_compute_progress', store=True)
    delivered_count = fields.Integer('Delivered', compute='_compute_progress', store=True)
    progress = fields.Float('Progress %', compute='_compute_progress', store=True, aggregator='avg')
    next_eta = fields.Date('Next ETA', compute='_compute_progress', store=True)
    status_summary = fields.Selection(STATUSES + [('late', 'Overdue'), ('closed', 'Closed')], compute='_compute_progress',
                                      store=True, string='Status')
    is_overdue = fields.Boolean(compute='_compute_progress', store=True)
    purchase_order_ids = fields.Many2many('purchase.order', compute='_compute_documents', string='Purchase Orders')
    picking_ids = fields.Many2many('stock.picking', compute='_compute_documents', string='Transfers')
    purchase_count = fields.Integer(compute='_compute_documents')
    picking_count = fields.Integer(compute='_compute_documents')
    public_url = fields.Char('Tracking link', compute='_compute_public_url')

    _sql_constraints = [('sale_order_uniq', 'unique(sale_order_id)', 'This Sales Order is already tracked.')]

    @api.depends('line_ids.status', 'line_ids.eta', 'eta_override', 'state')
    def _compute_progress(self):
        today = fields.Date.context_today(self)
        rank = {key: index for index, (key, _label) in enumerate(STATUSES)}
        for order in self:
            lines = order.line_ids
            pending = lines.filtered(lambda l: l.status != 'delivered')
            order.line_count = len(lines)
            order.delivered_count = len(lines) - len(pending)
            order.progress = 100.0 * order.delivered_count / len(lines) if lines else 0.0
            etas = [l.eta for l in pending if l.eta]
            order.next_eta = min(etas) if etas else False
            order.overall_eta = order.eta_override or (max(l.eta for l in lines if l.eta) if any(l.eta for l in lines) else False)
            order.is_overdue = bool(order.state == 'open' and any(eta < today for eta in etas))
            if order.state == 'closed':
                order.status_summary = 'closed'
            elif order.is_overdue:
                order.status_summary = 'late'
            else:
                # the least advanced item tells where the order is
                order.status_summary = min(pending.mapped('status'), key=lambda s: rank[s]) if pending else 'delivered'

    def _compute_documents(self):
        for order in self:
            sale = order.sale_order_id
            purchases = order.line_ids.purchase_line_id.order_id
            if sale:
                purchases |= sale._get_purchase_orders() if hasattr(sale, '_get_purchase_orders') else self.env['purchase.order']
            order.purchase_order_ids = purchases
            order.purchase_count = len(purchases)
            order.picking_ids = sale.picking_ids | purchases.picking_ids
            order.picking_count = len(order.picking_ids)

    def _compute_public_url(self):
        base = self.get_base_url()
        for order in self:
            order.public_url = '%s/track?po=%s' % (base, order.name) if order.name else False

    # ------------------------------------------------------------------
    # From the Sales Order
    # ------------------------------------------------------------------

    @api.model
    def _create_from_sale_order(self, sale):
        if not sale or self.sudo().search_count([('sale_order_id', '=', sale.id)]):
            return self.browse()
        contact = sale.partner_id if sale.partner_id.parent_id else sale.partner_invoice_id
        order = self.sudo().create({
            'name': (sale.client_order_ref or sale.name).strip(),
            'sale_order_id': sale.id,
            'partner_id': sale.partner_id.commercial_partner_id.id,
            'contact_name': contact.name if contact != sale.partner_id.commercial_partner_id else sale.partner_id.name,
            'contact_email': sale.partner_id.email or contact.email,
            'user_id': sale.user_id.id,
            'payment_terms': sale.payment_term_id.name,
            'po_date': fields.Date.to_date(sale.date_order) if sale.date_order else fields.Date.context_today(self),
            'eta_override': fields.Date.to_date(sale.commitment_date) if sale.commitment_date else False,
        })
        order._sync_lines()
        order.message_post(body=_('Created from %s.', sale._get_html_link()))
        if sale.partner_id.email:
            order.subscriber_ids = [(0, 0, {'email': sale.partner_id.email, 'confirmed': True})]
        order._notify_internal(_('New order to track: %(po)s for %(client)s', po=order.name, client=order.partner_id.name),
                               order._items_summary_html())
        return order

    def _sync_lines(self):
        """ Add the Sales Order items not tracked yet. """
        Line = self.env['technoai.tracking.line'].sudo()
        for order in self:
            sale = order.sale_order_id
            if not sale:
                continue
            known = order.line_ids.sale_line_id
            default_eta = order.eta_override or fields.Date.context_today(self) + timedelta(days=14)
            number = max(order.line_ids.mapped('line_number') or [0])
            for sale_line in sale.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment and l not in known):
                number += 1
                line = Line.create({
                    'order_id': order.id,
                    'line_number': number,
                    'sale_line_id': sale_line.id,
                    'name': sale_line.name.split('\n')[0] if sale_line.name else sale_line.product_id.display_name,
                    'product_id': sale_line.product_id.id,
                    'quantity': sale_line.product_uom_qty,
                    'uom': sale_line.product_uom.name,
                    'unit_price': sale_line.price_unit,
                    'eta': default_eta,
                })
                line._link_purchase_line()
        return True

    def action_sync_lines(self):
        self._sync_lines()
        self.line_ids._link_purchase_line()
        return True

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _update_state(self):
        """ Closed once every item is delivered, open again when one goes back. """
        for order in self:
            done = bool(order.line_ids) and all(line.status == 'delivered' for line in order.line_ids)
            if done and order.state == 'open':
                order.write({'state': 'closed', 'closed_date': fields.Date.context_today(self)})
                order._notify_internal(_('Order complete: %s', order.name), order._items_summary_html(), closed=True)
                order._notify_subscribers(_('Your order %s is complete', order.name),
                                          _('All items of your purchase order %s have been delivered.', order.name))
            elif not done and order.state == 'closed':
                order.write({'state': 'open', 'closed_date': False})

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _items_summary_html(self):
        self.ensure_one()
        rows = Markup('').join(
            Markup('<tr><td style="padding:4px 10px 4px 0">%s</td><td style="padding:4px 10px">%s</td><td style="padding:4px 10px">%s</td>'
                   '<td style="padding:4px 0">%s</td></tr>') % (
                line.line_number, line.name, PUBLIC_LABELS.get(line.status), line.eta and fields.Date.to_string(line.eta) or '-')
            for line in self.line_ids)
        return Markup('<table style="border-collapse:collapse;font-size:13px"><tr><th align="left">#</th><th align="left">Item</th>'
                      '<th align="left">Status</th><th align="left">ETA</th></tr>%s</table>') % rows

    def _email_html(self, title, text, extra=None, public=True):
        self.ensure_one()
        link = Markup('<p><a href="%s" style="display:inline-block;background:#1F869E;color:#fff;padding:9px 16px;border-radius:5px;'
                      'text-decoration:none">%s</a></p>') % (self.public_url, _('Track your order')) if public else Markup('')
        return Markup('<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#24323a">'
                      '<h2 style="font-size:18px;margin:0 0 10px">%s</h2><p>%s</p>%s%s'
                      '<p style="color:#8a99a1;font-size:12px">Techno AI order tracking</p></div>') % (title, text, extra or '', link)

    def _send_email(self, recipients, subject, body):
        recipients = sorted({email_normalize(email) for email in recipients if email_normalize(email)})
        if not recipients:
            return
        Mail = self.env['mail.mail'].sudo()
        for email in recipients:
            Mail.create({'subject': subject, 'body_html': body, 'email_to': email, 'auto_delete': True,
                         'model': self._name, 'res_id': self.id})

    def _internal_emails(self, closed=False):
        params = self.env['ir.config_parameter'].sudo()
        key = 'technoai_tracking.closed_emails' if closed else 'technoai_tracking.internal_emails'
        value = params.get_param(key) or ''
        return [email.strip() for email in value.replace(';', ',').split(',') if email.strip()]

    def _notify_internal(self, subject, extra=None, closed=False):
        """ The internal mailboxes by email, the sales person in the ERP (inbox and push). """
        for order in self:
            order._send_email(order._internal_emails(closed), subject,
                              order._email_html(subject, _('%(client)s, Sales Order %(so)s.', client=order.partner_id.name,
                                                           so=order.sale_order_id.name or '-'), extra, public=False))
            if order.user_id:
                order.sudo().with_context(mail_notify_author=True).message_notify(
                    author_id=self.env.ref('base.partner_root').id,
                    partner_ids=order.user_id.partner_id.ids,
                    subject=subject,
                    body=Markup('<p>%s</p>') % subject,
                    subtype_xmlid='mail.mt_comment',
                    email_layout_xmlid='mail.mail_notification_light',
                )

    def _notify_subscribers(self, subject, text, extra=None):
        base = self.get_base_url()
        for order in self:
            for subscriber in order.subscriber_ids.filtered('confirmed'):
                stop = Markup('<p style="font-size:11px;color:#8a99a1"><a href="%s/track/unsubscribe/%s" style="color:#8a99a1">%s</a></p>') % (
                    base, subscriber.token, _('Stop these updates'))
                order._send_email([subscriber.email], subject, order._email_html(subject, text, extra) + stop)

    @api.model
    def _cron_late_items(self):
        """ Once a day: tell the sales person and the tracking mailbox about late items. """
        today = fields.Date.context_today(self)
        lines = self.env['technoai.tracking.line'].sudo().search([
            ('status', '!=', 'delivered'), ('eta', '<', today), ('order_id.state', '=', 'open'),
            '|', ('late_alert_date', '=', False), ('late_alert_date', '<', today)])
        for order in lines.order_id:
            late = lines.filtered(lambda l: l.order_id == order)
            order._notify_internal(_('%(count)s late item(s) on %(po)s', count=len(late), po=order.name),
                                   Markup('<p>%s</p>') % ', '.join(late.mapped('name')))
            late.write({'late_alert_date': today})

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_open_sale_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order', 'res_id': self.sale_order_id.id, 'view_mode': 'form'}

    def action_open_purchases(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Purchase Orders'), 'res_model': 'purchase.order',
                'domain': [('id', 'in', self.purchase_order_ids.ids)], 'view_mode': 'list,form'}

    def action_open_pickings(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Transfers'), 'res_model': 'stock.picking',
                'domain': [('id', 'in', self.picking_ids.ids)], 'view_mode': 'list,form'}

    def action_open_public_page(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.public_url, 'target': 'new'}

    @api.model
    def get_dashboard_data(self):
        """ The figures of the Order Tracking dashboard. """
        Line = self.env['technoai.tracking.line']
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        open_lines = Line.search([('order_id.state', '=', 'open')])
        by_status = {key: 0 for key, _label in STATUSES}
        for line in open_lines:
            by_status[line.status] += 1
        by_status['delivered'] = Line.search_count([('status', '=', 'delivered'), ('last_update', '>=', month_start)])
        orders = self.search([('state', '=', 'open')], order='is_overdue desc, next_eta asc', limit=40)
        return {
            'open_orders': self.search_count([('state', '=', 'open')]),
            'on_the_way': len(open_lines.filtered(lambda l: l.status != 'delivered')),
            'late_items': len(open_lines.filtered(lambda l: l.status != 'delivered' and l.eta and l.eta < today)),
            'delivered_month': self.search_count([('state', '=', 'closed'), ('closed_date', '>=', month_start)]),
            'statuses': [{'key': key, 'label': label, 'count': by_status.get(key, 0)} for key, label in STATUSES],
            'orders': [{
                'id': order.id, 'po': order.name, 'so': order.sale_order_id.name or '', 'client': order.partner_id.name,
                'user': order.user_id.name or '', 'items': order.line_count, 'delivered': order.delivered_count,
                'progress': round(order.progress), 'next_eta': order.next_eta and fields.Date.to_string(order.next_eta) or '',
                'late': order.is_overdue, 'status': dict(self._fields['status_summary'].selection).get(order.status_summary, ''),
                'status_key': order.status_summary,
            } for order in orders],
        }


class TrackingSubscriber(models.Model):
    """ An email address that asked for updates on an order, from the tracking page or the Sales Order. """
    _name = 'technoai.tracking.subscriber'
    _description = 'Tracking update subscriber'
    _rec_name = 'email'

    order_id = fields.Many2one('technoai.tracking.order', required=True, ondelete='cascade', index=True)
    email = fields.Char(required=True)
    confirmed = fields.Boolean(help='Updates go only to addresses confirmed by the link sent to them.')
    token = fields.Char(default=lambda self: secrets.token_urlsafe(24), copy=False, index=True)

    _sql_constraints = [('order_email_uniq', 'unique(order_id, email)', 'This address already gets updates for this order.')]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['email'] = email_normalize(vals.get('email') or '') or vals.get('email')
            if not vals.get('email') or '@' not in vals['email']:
                raise UserError(_('Enter a valid email address.'))
        return super().create(vals_list)

    def _send_confirmation(self):
        for subscriber in self:
            order = subscriber.order_id
            url = '%s/track/confirm/%s' % (order.get_base_url(), subscriber.token)
            body = Markup('<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#24323a"><p>%s</p>'
                          '<p><a href="%s" style="display:inline-block;background:#1F869E;color:#fff;padding:9px 16px;border-radius:5px;'
                          'text-decoration:none">%s</a></p><p style="color:#8a99a1;font-size:12px">%s</p></div>') % (
                _('Please confirm that you want email updates for your purchase order %s.', order.name), url,
                _('Confirm updates'), _('If you did not ask for this, ignore this email.'))
            order._send_email([subscriber.email], _('Confirm updates for order %s', order.name), body)
