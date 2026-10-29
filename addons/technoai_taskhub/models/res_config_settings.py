from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    taskhub_whatsapp_provider = fields.Selection(
        [('link', 'WhatsApp link (no account needed)'),
         ('cloud', 'WhatsApp Cloud API (Meta)'),
         ('twilio', 'Twilio'),
         ('green', 'Green API')],
        'WhatsApp provider', default='link', config_parameter='technoai_taskhub.whatsapp_provider')
    taskhub_wa_cloud_token = fields.Char('Cloud API access token', config_parameter='technoai_taskhub.wa_cloud_token')
    taskhub_wa_cloud_phone_id = fields.Char('Cloud API phone number ID', config_parameter='technoai_taskhub.wa_cloud_phone_id')
    taskhub_wa_twilio_sid = fields.Char('Twilio account SID', config_parameter='technoai_taskhub.wa_twilio_sid')
    taskhub_wa_twilio_token = fields.Char('Twilio auth token', config_parameter='technoai_taskhub.wa_twilio_token')
    taskhub_wa_twilio_from = fields.Char('Twilio WhatsApp number', config_parameter='technoai_taskhub.wa_twilio_from')
    taskhub_wa_green_instance = fields.Char('Green API instance ID', config_parameter='technoai_taskhub.wa_green_instance')
    taskhub_wa_green_token = fields.Char('Green API token', config_parameter='technoai_taskhub.wa_green_token')
