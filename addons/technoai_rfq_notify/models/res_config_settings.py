from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rfq_notify_interval = fields.Integer('Check mailboxes every (minutes)', default=1)
    rfq_notify_remind_minutes = fields.Integer(
        'Remind when not opened after (minutes)', config_parameter='technoai_rfq_notify.remind_minutes', default=15,
        help='0 turns reminders off.')
    rfq_notify_escalate = fields.Boolean(
        'Then tell the manager', config_parameter='technoai_rfq_notify.escalate', default=True,
        help="After twice that time, the employee's manager (Employees app) is told as well.")

    @api.model
    def get_values(self):
        values = super().get_values()
        cron = self.env.ref('technoai_rfq_notify.ir_cron_check_mailboxes', raise_if_not_found=False)
        values['rfq_notify_interval'] = cron.interval_number if cron else 1
        return values

    def set_values(self):
        super().set_values()
        cron = self.env.ref('technoai_rfq_notify.ir_cron_check_mailboxes', raise_if_not_found=False)
        if cron and self.rfq_notify_interval > 0:
            cron.sudo().write({'interval_number': self.rfq_notify_interval, 'interval_type': 'minutes'})
