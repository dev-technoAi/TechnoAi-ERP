import base64

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tracking_ids = fields.One2many('technoai.tracking.order', 'sale_order_id', 'Order tracking')
    tracking_label = fields.Char(compute='_compute_tracking_label')

    @api.depends('tracking_ids.delivered_count', 'tracking_ids.line_count')
    def _compute_tracking_label(self):
        for order in self:
            tracking = order.tracking_ids[:1]
            order.tracking_label = '%s of %s' % (tracking.delivered_count, tracking.line_count) if tracking else False

    def action_confirm(self):
        result = super().action_confirm()
        Tracking = self.env['technoai.tracking.order']
        for order in self.filtered(lambda o: o.state == 'sale'):
            Tracking._create_from_sale_order(order)
        return result

    def action_open_tracking(self):
        self.ensure_one()
        tracking = self.tracking_ids[:1] or self.env['technoai.tracking.order']._create_from_sale_order(self)
        return {'type': 'ir.actions.act_window', 'res_model': 'technoai.tracking.order', 'res_id': tracking.id, 'view_mode': 'form'}

    def _tai_tracking_url(self):
        """ The public tracking link printed with a QR code on the order documents. """
        self.ensure_one()
        tracking = self.sudo().tracking_ids[:1]
        return tracking.public_url if tracking else False

    def _tai_tracking_qr(self):
        """ The QR code of the tracking link, embedded in the PDF. """
        url = self._tai_tracking_url()
        if not url:
            return False
        png = self.env['ir.actions.report'].barcode('QR', url, width=240, height=240)
        return 'data:image/png;base64,%s' % base64.b64encode(png).decode()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # items added to a confirmed order join its tracking
        lines.order_id.filtered(lambda o: o.state == 'sale').sudo().tracking_ids._sync_lines()
        return lines
