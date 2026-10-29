from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    taskhub_open_task_count = fields.Integer('Open tasks', compute='_compute_taskhub_open_task_count')
    taskhub_is_admin = fields.Boolean(related='user_id.taskhub_is_admin', string='Task Hub admin')

    @api.depends('user_id')
    def _compute_taskhub_open_task_count(self):
        counts = dict(self.env['taskhub.task']._read_group(
            [('state', '!=', 'done'), ('user_id', 'in', self.user_id.ids)], ['user_id'], ['__count']))
        for employee in self:
            employee.taskhub_open_task_count = counts.get(employee.user_id, 0)

    def action_open_taskhub_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'taskhub.task',
            'view_mode': 'list,kanban,form',
            'domain': [('user_id', '=', self.user_id.id)],
            'context': {'search_default_open': 1},
        }
