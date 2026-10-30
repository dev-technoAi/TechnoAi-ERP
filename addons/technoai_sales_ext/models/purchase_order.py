from odoo import fields, models

from .sale_order import TAX_DISPLAY


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    tai_tax_display = fields.Selection(TAX_DISPLAY, 'Amounts', default='excl', required=True, copy=False)
