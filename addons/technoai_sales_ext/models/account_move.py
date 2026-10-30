from odoo import fields, models

from .sale_order import TAX_DISPLAY


class AccountMove(models.Model):
    _inherit = 'account.move'

    tai_tax_display = fields.Selection(TAX_DISPLAY, 'Amounts', default='excl', required=True, copy=False)
