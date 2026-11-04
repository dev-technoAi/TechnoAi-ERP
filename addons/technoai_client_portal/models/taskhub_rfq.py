from odoo import fields, models


class TaskhubRfq(models.Model):
    _inherit = 'taskhub.rfq'

    source = fields.Selection(selection_add=[('portal', 'Client portal')], ondelete={'portal': 'set default'})
