from odoo import _, fields, models
from odoo.exceptions import UserError


class TaskhubReset(models.TransientModel):
    _name = 'taskhub.reset'
    _description = 'Reset Task Hub data'

    confirm = fields.Char('Type RESET to confirm')

    def _models_to_clear(self):
        """ Task Hub records removed by a reset; other parts of Task Hub extend this. """
        return [
            ('taskhub.task', [('active', 'in', [True, False])]),
            ('taskhub.template', [('is_standard', '=', False), ('active', 'in', [True, False])]),
        ]

    def action_reset(self):
        self.ensure_one()
        if not self.env.user.has_group('technoai_taskhub.group_taskhub_admin'):
            raise UserError(_('Only Task Hub administrators can reset Task Hub data.'))
        if (self.confirm or '').strip() != 'RESET':
            raise UserError(_('Type RESET in capital letters to confirm.'))
        removed = []
        for model, domain in self._models_to_clear():
            records = self.env[model].sudo().with_context(active_test=False).search(domain)
            removed.append('%s %s' % (len(records), self.env[model]._description))
            records.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Task Hub data reset'),
                'message': _('Removed: %s. Standard templates, departments and the team are kept.', ', '.join(removed)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
