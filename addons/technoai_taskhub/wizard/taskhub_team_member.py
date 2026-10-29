from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TaskhubTeamMember(models.TransientModel):
    _name = 'taskhub.team.member'
    _description = 'Add a Task Hub team member'

    name = fields.Char('Full name', required=True)
    email = fields.Char('Work email', required=True)
    department_id = fields.Many2one('hr.department', 'Department')
    role = fields.Selection([('member', 'Member'), ('admin', 'Admin')], default='member', required=True)
    phone = fields.Char('Phone / WhatsApp')
    job_title = fields.Char('Job title')

    @api.onchange('email')
    def _onchange_email(self):
        if self.email:
            self.email = self.email.strip().lower()

    def action_create(self):
        """ One step: the Techno AI login, the employee and the Task Hub role. """
        self.ensure_one()
        email = self.email.strip().lower()
        Users = self.env['res.users'].with_context(no_reset_password=True)
        if Users.search_count([('login', '=ilike', email)]):
            raise UserError(_('A user with the login %s already exists.', email))
        user = Users.create({
            'name': self.name,
            'login': email,
            'email': email,
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        user.taskhub_is_admin = self.role == 'admin'
        employee = user.employee_id or self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
        employee_vals = {
            'name': self.name,
            'work_email': email,
            'department_id': self.department_id.id,
            'mobile_phone': self.phone,
            'job_title': self.job_title,
        }
        if employee:
            employee.write(employee_vals)
        else:
            employee = self.env['hr.employee'].create(dict(employee_vals, user_id=user.id))
        # the welcome email with the password link goes out once outgoing mail is set up
        try:
            user.action_reset_password()
        except UserError:
            pass
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Team member created'),
                'message': _('%s can now sign in to Techno AI.', self.name),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
