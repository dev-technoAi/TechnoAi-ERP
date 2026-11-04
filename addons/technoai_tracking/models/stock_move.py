from odoo import _, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _tracking_lines(self):
        """ The tracked items these moves bring in (purchase) or take out (sale). """
        Line = self.env['technoai.tracking.line'].sudo()
        sale_lines = self.sale_line_id | self.move_dest_ids.sale_line_id
        domain = ['|', ('purchase_line_id', 'in', self.purchase_line_id.ids), ('sale_line_id', 'in', sale_lines.ids)]
        return Line.search(domain) if (self.purchase_line_id or sale_lines) else Line

    def _action_assign(self, force_qty=False):
        result = super()._action_assign(force_qty=force_qty)
        for move in self.filtered(lambda m: m.state == 'assigned' and m.picking_code == 'outgoing' and m.sale_line_id):
            move._tracking_lines().filtered(lambda l: l.sale_line_id == move.sale_line_id)._advance(
                'ready_for_delivery', _('reserved on %s', move.picking_id.name))
        return result

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        for move in moves.filtered(lambda m: m.state == 'done'):
            if move.picking_code == 'incoming' and move.purchase_line_id:
                move._tracking_lines().filtered(lambda l: l.purchase_line_id == move.purchase_line_id
                                                or l.sale_line_id in move.move_dest_ids.sale_line_id)._advance(
                    'in_inventory', _('received on %s', move.picking_id.name))
            elif move.picking_code == 'outgoing' and move.sale_line_id:
                sale_line = move.sale_line_id
                lines = move._tracking_lines().filtered(lambda l: l.sale_line_id == sale_line)
                if sale_line.qty_delivered >= sale_line.product_uom_qty:
                    lines._advance('delivered', _('delivered with %s', move.picking_id.name))
                else:
                    lines.filtered(lambda l: l.status != 'delivered').write({
                        'internal_remarks': _('Partly delivered: %(done)s of %(total)s', done=sale_line.qty_delivered,
                                              total=sale_line.product_uom_qty)})
        return moves


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        result = super().button_confirm()
        # a confirmed supplier order links its supplier to the tracked items
        self.env['technoai.tracking.line'].sudo().search(
            [('purchase_line_id', '=', False), ('order_id.state', '=', 'open')])._link_purchase_line()
        return result
