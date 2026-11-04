from datetime import timedelta
from urllib.parse import quote

from markupsafe import Markup

from odoo import _, fields, models

CARRIERS = [
    ('dhl', 'DHL'),
    ('aramex', 'Aramex'),
    ('fedex', 'FedEx'),
    ('ups', 'UPS'),
    ('smsa', 'SMSA'),
    ('own', 'Supplier delivery'),
    ('other', 'Other'),
]
CARRIER_LINKS = {
    'dhl': 'https://www.dhl.com/global-en/home/tracking.html?tracking-id=%s',
    'aramex': 'https://www.aramex.com/track/results?ShipmentNumber=%s',
    'fedex': 'https://www.fedex.com/fedextrack/?trknbr=%s',
    'ups': 'https://www.ups.com/track?tracknum=%s',
    'smsa': 'https://www.smsaexpress.com/trackingdetails?tracknumbers=%s',
}


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    tai_vendor_quoted_date = fields.Datetime('Supplier sent prices', readonly=True, copy=False)
    tai_vendor_accepted_date = fields.Datetime('Supplier accepted', readonly=True, copy=False, tracking=True)

    def _tai_vendor_partner(self):
        return self.partner_id.commercial_partner_id

    def _tai_notify_buyer(self, subject, body):
        """ The buyer hears about what the supplier did in the portal (ERP inbox and push). """
        for order in self:
            order.message_post(body=body, subtype_xmlid='mail.mt_note')
            if order.user_id:
                order.with_context(mail_notify_author=True).message_notify(
                    author_id=self.env.ref('base.partner_root').id, partner_ids=order.user_id.partner_id.ids,
                    subject=subject, body=body, subtype_xmlid='mail.mt_comment',
                    email_layout_xmlid='mail.mail_notification_light')

    def _tai_index_vendor_prices(self):
        """ Prices the supplier sent are sourcing history: Known suppliers ranks them on the next quotation. """
        Sourcing = self.env['taskhub.sourcing'].sudo()
        for line in self.order_line.filtered(lambda l: not l.display_type and not l.tai_vendor_cannot_quote and l.price_unit > 0):
            key = 'supplier-portal-line-%s' % line.id
            values = {
                'name': line.name.split('\n')[0] if line.name else line.product_id.display_name,
                'supplier_id': line.order_id._tai_vendor_partner().id,
                'unit_cost': line.price_unit,
                'currency_id': line.order_id.currency_id.id,
                'status': 'quoted',
                'notes': ' / '.join(filter(None, [
                    _('Sent in the supplier portal on %s', line.order_id.name),
                    line.tai_vendor_lead_days and _('lead time %s days', line.tai_vendor_lead_days),
                    line.tai_vendor_note])),
                'source_key': key,
            }
            existing = Sourcing.search([('source_key', '=', key)], limit=1)
            if existing:
                existing.write(values)
            else:
                Sourcing.create(values)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    tai_vendor_lead_days = fields.Integer('Supplier lead time (days)', copy=False)
    tai_vendor_note = fields.Char('Supplier note', copy=False)
    tai_vendor_cannot_quote = fields.Boolean('Supplier cannot quote', copy=False)
    tai_ship_status = fields.Selection([('ready', 'Ready to ship'), ('shipped', 'Shipped')], 'Shipment', copy=False)
    tai_ship_date = fields.Date('Ship date', copy=False)
    tai_carrier = fields.Selection(CARRIERS, 'Carrier', copy=False)
    tai_tracking_ref = fields.Char('Tracking number or link', copy=False)
    tai_tracking_url = fields.Char('Tracking link', compute='_compute_tai_tracking_url')

    def _compute_tai_tracking_url(self):
        for line in self:
            ref = (line.tai_tracking_ref or '').strip()
            if ref.startswith('http'):
                line.tai_tracking_url = ref
            elif ref and line.tai_carrier in CARRIER_LINKS:
                line.tai_tracking_url = CARRIER_LINKS[line.tai_carrier] % quote(ref.replace(' ', ''))
            else:
                line.tai_tracking_url = False

    def _tai_apply_shipment(self):
        """ Move the client's tracked items on: ready to ship, then in transit with the shipment link. """
        Tracking = self.env['technoai.tracking.line'].sudo()
        for line in self.filtered('tai_ship_status'):
            items = Tracking.search(['|', ('purchase_line_id', '=', line.id),
                                     ('sale_line_id', 'in', (line.sale_line_id | line.move_dest_ids.sale_line_id).ids)])
            if not items:
                continue
            supplier = line.order_id._tai_vendor_partner().name
            if line.tai_ship_status == 'ready':
                items._advance('ready_to_ship', _('ready at %s (supplier portal)', supplier))
            else:
                values = {}
                if line.tai_tracking_url:
                    values['shipment_link'] = line.tai_tracking_url
                if line.tai_ship_date:
                    lead = 5 if line.tai_carrier and line.tai_carrier != 'own' else 1
                    values['eta'] = max(line.tai_ship_date + timedelta(days=lead), line.date_planned.date() if line.date_planned else line.tai_ship_date)
                if values:
                    items.write(values)
                items._advance('in_transit', _('shipped by %s (supplier portal)', supplier))

    def _tai_shipment_summary(self):
        self.ensure_one()
        status = dict(self._fields['tai_ship_status'].selection).get(self.tai_ship_status, '')
        carrier = dict(self._fields['tai_carrier'].selection).get(self.tai_carrier, '')
        return Markup('%s: <b>%s</b>%s%s') % (
            self.name.split('\n')[0], status,
            Markup(' · %s') % carrier if carrier else '',
            Markup(' · <a href="%s">%s</a>') % (self.tai_tracking_url, self.tai_tracking_ref) if self.tai_tracking_url
            else (Markup(' · %s') % self.tai_tracking_ref if self.tai_tracking_ref else ''))
