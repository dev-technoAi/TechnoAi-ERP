from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    tai_remarks = fields.Text('Remarks')


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_new_picking_values(self):
        values = super()._get_new_picking_values()
        remarks = self.sale_line_id.order_id[:1].tai_remarks
        if remarks:
            values['tai_remarks'] = remarks
        return values
