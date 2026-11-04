from markupsafe import Markup

from odoo import _, api, fields, models

STATUSES = [
    ('processing', 'Processing'),
    ('ready_to_ship', 'Ready to Ship from Supplier'),
    ('in_transit', 'In Transit'),
    ('in_inventory', 'In Inventory'),
    ('ready_for_delivery', 'Ready for Delivery'),
    ('delivered', 'Delivered'),
]
# what the client sees on the tracking page and in emails
PUBLIC_LABELS = {
    'processing': 'Processing',
    'ready_to_ship': 'Ready to ship',
    'in_transit': 'In transit',
    'in_inventory': 'In our warehouse',
    'ready_for_delivery': 'Ready for delivery',
    'delivered': 'Delivered',
}
RANK = {key: index for index, (key, _label) in enumerate(STATUSES)}


class TrackingLine(models.Model):
    _name = 'technoai.tracking.line'
    _description = 'Tracked order item'
    _order = 'order_id, line_number, id'

    order_id = fields.Many2one('technoai.tracking.order', required=True, ondelete='cascade', index=True)
    line_number = fields.Integer('#', default=1)
    sale_line_id = fields.Many2one('sale.order.line', 'Sales Order line', ondelete='set null', index=True)
    purchase_line_id = fields.Many2one('purchase.order.line', 'Purchase line', ondelete='set null', index=True)
    product_id = fields.Many2one('product.product', 'Product')
    name = fields.Char('Item', required=True)
    quantity = fields.Float(default=1.0, digits='Product Unit of Measure')
    uom = fields.Char('Unit')
    unit_price = fields.Float('Unit price', digits='Product Price')
    supplier_id = fields.Many2one('res.partner', 'Supplier', compute='_compute_supplier', store=True, readonly=False)
    status = fields.Selection(STATUSES, default='processing', required=True, index=True)
    status_rank = fields.Integer(compute='_compute_status_rank', store=True)
    eta = fields.Date('ETA')
    shipment_link = fields.Char('Shipment tracking link')
    internal_remarks = fields.Char('Internal remarks')
    last_update = fields.Datetime('Last update', default=fields.Datetime.now, readonly=True)
    auto_note = fields.Char('Last change', readonly=True)
    late_alert_date = fields.Date(readonly=True, copy=False)
    is_late = fields.Boolean('Late', compute='_compute_is_late')
    public_status = fields.Char(compute='_compute_public_status')

    @api.depends('purchase_line_id.partner_id')
    def _compute_supplier(self):
        for line in self:
            line.supplier_id = line.purchase_line_id.partner_id or line.supplier_id

    @api.depends('status')
    def _compute_status_rank(self):
        for line in self:
            line.status_rank = RANK.get(line.status, 0)

    @api.depends('status')
    def _compute_public_status(self):
        for line in self:
            line.public_status = PUBLIC_LABELS.get(line.status)

    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for line in self:
            line.is_late = bool(line.status != 'delivered' and line.eta and line.eta < today)

    def _link_purchase_line(self):
        """ The supplier's purchase line of the item: linked by the procurement, by the order's origin, or by the
        Purchase Orders that Task Hub made from the quotation of this Sales Order. """
        PurchaseLine = self.env['purchase.order.line'].sudo()
        for line in self.filtered(lambda l: not l.purchase_line_id and l.sale_line_id):
            sale_line = line.sale_line_id
            found = PurchaseLine.search([('sale_line_id', '=', sale_line.id)], limit=1)
            if not found:
                found = sale_line.move_ids.move_orig_ids.purchase_line_id[:1]
            if not found:
                sale = sale_line.order_id
                orders = self.env['purchase.order'].sudo().search([('origin', 'ilike', sale.name), ('state', '!=', 'cancel')])
                if 'taskhub.quotation' in self.env:
                    quotes = self.env['taskhub.quotation'].sudo().search([('sale_order_id', '=', sale.id)])
                    orders |= quotes.purchase_order_ids.filtered(lambda o: o.state != 'cancel')
                candidates = orders.order_line.filtered(lambda l: not l.display_type)
                found = candidates.filtered(lambda l: l.product_id == sale_line.product_id and l.product_id.name not in ('Quoted item', 'Sourced item'))[:1] \
                    or candidates.filtered(lambda l: (l.name or '').strip().lower() == (line.name or '').strip().lower())[:1]
            if found:
                line.purchase_line_id = found

    def _advance(self, status, note):
        """ Move items forward only (never back), when a receipt or a delivery says so. """
        for line in self.filtered(lambda l: RANK[status] > RANK[l.status]):
            line.with_context(tracking_auto_note=note).write({'status': status})

    def write(self, vals):
        old = {line.id: (line.status, line.eta) for line in self} if {'status', 'eta'} & set(vals) else {}
        if 'status' in vals:
            vals = dict(vals, last_update=fields.Datetime.now(),
                        auto_note=self.env.context.get('tracking_auto_note') or _('Set by %s', self.env.user.name))
        result = super().write(vals)
        if old:
            self._after_change(old)
        return result

    def _after_change(self, old):
        for order in self.order_id:
            changes = []
            for line in self.filtered(lambda l: l.order_id == order):
                status, eta = old[line.id]
                if status != line.status:
                    changes.append((line, status))
                elif eta != line.eta:
                    order.message_post(body=_('Item %(number)s %(name)s: ETA %(old)s > %(new)s', number=line.line_number,
                                              name=line.name, old=eta or '-', new=line.eta or '-'), subtype_xmlid='mail.mt_note')
            if not changes:
                continue
            labels = dict(STATUSES)
            text = Markup('<br/>').join(
                Markup('Item %s %s: %s &gt; <b>%s</b>%s') % (line.line_number, line.name, labels[status], labels[line.status],
                                                             Markup(' <i>(%s)</i>') % line.auto_note if line.auto_note else '')
                for line, status in changes)
            order.message_post(body=text, subtype_xmlid='mail.mt_note')
            order._notify_internal(_('Status update on %s', order.name), Markup('<p>%s</p>') % text)
            public_rows = Markup('<br/>').join(
                Markup('%s: <b>%s</b>%s') % (line.name, PUBLIC_LABELS[line.status],
                                             Markup(' (expected %s)') % line.eta if line.eta and line.status != 'delivered' else '')
                for line, _status in changes)
            order._notify_subscribers(_('Update on your order %s', order.name),
                                      _('There is news on your purchase order %s:', order.name), Markup('<p>%s</p>') % public_rows)
            order._update_state()
