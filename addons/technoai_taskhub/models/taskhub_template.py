from odoo import api, fields, models

from .taskhub_task import PRIORITIES


class TaskhubTemplate(models.Model):
    _name = 'taskhub.template'
    _description = 'Task Hub Template'
    _order = 'is_standard, department_id, sequence, name'

    name = fields.Char('Title', required=True)
    description = fields.Html()
    priority = fields.Selection(PRIORITIES, default='medium', required=True)
    department_id = fields.Many2one('hr.department', 'Department')
    check_ids = fields.One2many('taskhub.template.check', 'template_id', 'Checklist', copy=True)
    check_count = fields.Integer('Subtasks', compute='_compute_check_count')
    is_standard = fields.Boolean('Standard', readonly=True, help='Shipped with Task Hub; kept when Task Hub data is reset.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.depends('check_ids')
    def _compute_check_count(self):
        for template in self:
            template.check_count = len(template.check_ids)

    def action_use_template(self):
        """ Create a task from the template and open it. """
        self.ensure_one()
        task = self.env['taskhub.task'].create({
            'name': self.name,
            'description': self.description,
            'priority': self.priority,
            'department_id': self.department_id.id,
            'template_id': self.id,
            'check_ids': [(0, 0, {'name': check.name, 'sequence': check.sequence}) for check in self.check_ids],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'taskhub.task',
            'res_id': task.id,
            'view_mode': 'form',
            'target': 'current',
        }


class TaskhubTemplateCheck(models.Model):
    _name = 'taskhub.template.check'
    _description = 'Task Hub Template Step'
    _order = 'sequence, id'

    template_id = fields.Many2one('taskhub.template', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Step', required=True)
