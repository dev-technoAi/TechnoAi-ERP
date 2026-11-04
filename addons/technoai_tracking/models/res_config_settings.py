from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tracking_internal_emails = fields.Char(
        'Tracking mailbox', config_parameter='technoai_tracking.internal_emails',
        help='Comma-separated: told about new orders, status changes and late items.')
    tracking_closed_emails = fields.Char(
        'Completed orders', config_parameter='technoai_tracking.closed_emails',
        help='Comma-separated: told when every item of an order is delivered (accounts, logistics...).')
