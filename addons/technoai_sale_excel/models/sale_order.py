from odoo import _, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_open_excel_import(self):
        """ The "Upload Excel" button of the Quotations list (called with no or the selected quotations). """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Order from Excel'),
            'res_model': 'sale.excel.import',
            'view_mode': 'form',
            'target': 'new',
        }
