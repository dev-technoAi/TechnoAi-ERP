from odoo import api, fields, models

ALERT_SOUNDS = [
    ('industrial-siren', 'Heavy Industrial Siren'),
    ('digital-matrix', 'Digital Matrix'),
    ('airport-chime', 'Airport Chime'),
    ('gentle-bell', 'Gentle Crystal Bell'),
    ('none', 'No sound'),
]


class ResUsers(models.Model):
    _inherit = 'res.users'

    taskhub_alert_sound = fields.Selection(ALERT_SOUNDS, 'Alert sound', default='industrial-siren')
    taskhub_alert_volume = fields.Integer('Alert volume (%)', default=80)
    taskhub_is_admin = fields.Boolean(
        'Task Hub admin', compute='_compute_taskhub_is_admin', inverse='_inverse_taskhub_is_admin')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['taskhub_alert_sound', 'taskhub_alert_volume']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['taskhub_alert_sound', 'taskhub_alert_volume']

    @api.depends('groups_id')
    def _compute_taskhub_is_admin(self):
        admin_group = self.env.ref('technoai_taskhub.group_taskhub_admin')
        for user in self:
            user.taskhub_is_admin = admin_group in user.groups_id

    def _inverse_taskhub_is_admin(self):
        admin_group = self.env.ref('technoai_taskhub.group_taskhub_admin')
        user_group = self.env.ref('technoai_taskhub.group_taskhub_user')
        for user in self:
            if user.taskhub_is_admin:
                user.groups_id = [(4, admin_group.id)]
            else:
                user.groups_id = [(3, admin_group.id), (4, user_group.id)]
