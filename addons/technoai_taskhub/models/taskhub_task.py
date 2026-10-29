from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.tools import html2plaintext

PRIORITIES = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('urgent', 'Urgent'),
]
PRIORITY_RANK = {key: rank for rank, (key, _label) in enumerate(PRIORITIES)}

# documents of the other Techno AI apps a task can point to
LINKABLE_MODELS = [
    ('res.partner', 'Contact'),
    ('crm.lead', 'Lead / Opportunity'),
    ('sale.order', 'Quotation / Sales Order'),
    ('purchase.order', 'RFQ / Purchase Order'),
    ('account.move', 'Invoice / Bill'),
    ('project.task', 'Project Task'),
]


class TaskhubTask(models.Model):
    _name = 'taskhub.task'
    _description = 'Task Hub Task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state_sequence, date_deadline asc, priority_rank desc, id desc'

    name = fields.Char('Task', required=True, tracking=True)
    description = fields.Html()
    priority = fields.Selection(PRIORITIES, default='medium', required=True, tracking=True)
    priority_rank = fields.Integer(compute='_compute_priority_rank', store=True)
    department_id = fields.Many2one('hr.department', 'Department', tracking=True)
    user_id = fields.Many2one(
        'res.users', 'Assigned to', tracking=True, default=lambda self: self.env.user,
        domain=[('share', '=', False)])
    assigned_by_id = fields.Many2one('res.users', 'Assigned by', default=lambda self: self.env.user, readonly=True)
    assigned_at = fields.Datetime(readonly=True)
    date_deadline = fields.Datetime('Due', tracking=True)
    state = fields.Selection(
        [('todo', 'To do'), ('in_progress', 'In progress'), ('done', 'Done')],
        default='todo', required=True, tracking=True, group_expand='_read_group_state')
    state_sequence = fields.Integer(compute='_compute_state_sequence', store=True)
    date_done = fields.Datetime('Completed on', readonly=True)
    check_ids = fields.One2many('taskhub.task.check', 'task_id', 'Checklist', copy=True)
    check_count = fields.Integer(compute='_compute_check_progress')
    check_done_count = fields.Integer(compute='_compute_check_progress')
    check_progress = fields.Char('Steps', compute='_compute_check_progress')
    partner_id = fields.Many2one('res.partner', 'Customer / Supplier', tracking=True)
    linked_ref = fields.Reference(selection='_selection_linked_ref', string='Linked to')
    template_id = fields.Many2one('taskhub.template', 'Created from template', readonly=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue')
    alert_snoozed_until = fields.Datetime(copy=False)
    alert_dismissed = fields.Boolean(copy=False)
    reminder_sent = fields.Boolean(copy=False)
    color = fields.Integer()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model
    def _selection_linked_ref(self):
        return [(model, label) for model, label in LINKABLE_MODELS if model in self.env]

    @api.depends('priority')
    def _compute_priority_rank(self):
        for task in self:
            task.priority_rank = PRIORITY_RANK.get(task.priority, 0)

    @api.depends('state')
    def _compute_state_sequence(self):
        order = {'in_progress': 0, 'todo': 1, 'done': 2}
        for task in self:
            task.state_sequence = order.get(task.state, 1)

    @api.depends('check_ids.status')
    def _compute_check_progress(self):
        for task in self:
            total = len(task.check_ids)
            done = len(task.check_ids.filtered(lambda c: c.status == 'completed'))
            task.check_count = total
            task.check_done_count = done
            task.check_progress = _('%(done)s of %(total)s steps', done=done, total=total) if total else ''

    @api.depends('date_deadline', 'state')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for task in self:
            task.is_overdue = bool(task.state != 'done' and task.date_deadline and task.date_deadline < now)

    def _search_is_overdue(self, operator, value):
        now = fields.Datetime.now()
        if (operator == '=') == bool(value):
            return [('state', '!=', 'done'), ('date_deadline', '<', now)]
        return ['|', '|', ('state', '=', 'done'), ('date_deadline', '=', False), ('date_deadline', '>=', now)]

    def _read_group_state(self, states, domain):
        # show every column on the kanban board, even empty ones
        return [key for key, _label in self._fields['state'].selection]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('user_id'):
                vals.setdefault('assigned_at', fields.Datetime.now())
        tasks = super().create(vals_list)
        for task in tasks:
            task._notify_assignee()
        return tasks

    def write(self, vals):
        if 'user_id' in vals:
            vals = dict(vals, assigned_by_id=self.env.uid, assigned_at=fields.Datetime.now())
        if 'date_deadline' in vals:
            vals = dict(vals, alert_dismissed=False, alert_snoozed_until=False, reminder_sent=False)
        if vals.get('state') == 'done':
            vals = dict(vals, date_done=fields.Datetime.now())
        elif vals.get('state') in ('todo', 'in_progress'):
            vals = dict(vals, date_done=False)
        res = super().write(vals)
        if 'user_id' in vals:
            for task in self:
                task._notify_assignee()
        return res

    def _notify_assignee(self):
        self.ensure_one()
        if not self.user_id or self.user_id == self.env.user:
            if self.user_id:
                self.message_subscribe(partner_ids=self.user_id.partner_id.ids)
            return
        self.message_subscribe(partner_ids=self.user_id.partner_id.ids)
        self.message_post(
            body=_('%(user)s assigned this task to you.', user=self.env.user.name),
            partner_ids=self.user_id.partner_id.ids,
            subtype_xmlid='mail.mt_comment',
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_mark_done(self):
        self.write({'state': 'done'})

    def action_reopen(self):
        self.write({'state': 'todo'})

    def action_snooze_alert(self, minutes=5):
        self.write({'alert_snoozed_until': fields.Datetime.now() + timedelta(minutes=int(minutes))})
        return True

    def action_dismiss_alert(self):
        self.write({'alert_dismissed': True})
        return True

    def action_save_as_template(self):
        self.ensure_one()
        template = self.env['taskhub.template'].create({
            'name': self.name,
            'description': self.description,
            'priority': self.priority,
            'department_id': self.department_id.id,
            'check_ids': [(0, 0, {'name': check.name, 'sequence': check.sequence}) for check in self.check_ids],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'taskhub.template',
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Tasks overview (client action)
    # ------------------------------------------------------------------

    @api.model
    def get_overview(self, show='everyone'):
        """ Data for the Tasks overview page: counters, the due alert and the task tabs. """
        user = self.env.user
        is_admin = user.has_group('technoai_taskhub.group_taskhub_admin')
        domain = []
        if show == 'mine' or not is_admin:
            domain = ['|', ('user_id', '=', user.id), ('create_uid', '=', user.id)]
        # "today" and "this week" follow the user's timezone; dates are stored in UTC
        now = fields.Datetime.now()
        tz = pytz.timezone(user.tz or 'UTC')
        local_now = pytz.utc.localize(now).astimezone(tz)
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start = local_midnight.astimezone(pytz.utc).replace(tzinfo=None)
        day_end = day_start + timedelta(days=1)
        week_start = day_start - timedelta(days=local_now.weekday())

        open_tasks = self.search(domain + [('state', '!=', 'done')])
        done_tasks = self.search(domain + [('state', '=', 'done')], limit=50, order='date_done desc')
        today = open_tasks.filtered(lambda t: t.date_deadline and day_start <= t.date_deadline < day_end)
        overdue = open_tasks.filtered(lambda t: t.date_deadline and t.date_deadline < now)

        alertable = (overdue | today).filtered(
            lambda t: t.date_deadline and t.date_deadline <= now + timedelta(minutes=15)
            and not t.alert_dismissed
            and (not t.alert_snoozed_until or t.alert_snoozed_until <= now)
            and (t.user_id == user or is_admin and show != 'mine'))
        alert = alertable.sorted(lambda t: (-t.priority_rank, t.date_deadline))[:1]

        return {
            'user_name': user.name.split(' ')[0],
            'is_admin': is_admin,
            'sound': user.taskhub_alert_sound or 'industrial-siren',
            'volume': user.taskhub_alert_volume or 80,
            'counts': {
                'due_today': len(today),
                'overdue': len(overdue),
                'open_rfqs': self._overview_open_rfq_count(),
                'done_week': self.search_count(domain + [('state', '=', 'done'), ('date_done', '>=', week_start)]),
            },
            'alert': alert and alert._overview_values(now)[0] or False,
            'tabs': {
                'todo': open_tasks._overview_values(now),
                'today': today._overview_values(now),
                'overdue': overdue._overview_values(now),
                'done': done_tasks._overview_values(now),
            },
        }

    @api.model
    def _overview_open_rfq_count(self):
        # filled in by the Email RFQs part of Task Hub
        return 0

    def _overview_values(self, now):
        priority_labels = dict(PRIORITIES)
        values = []
        for task in self:
            linked = task.linked_ref
            values.append({
                'id': task.id,
                'name': task.name,
                'description': html2plaintext(task.description or '').strip()[:240],
                'priority': task.priority,
                'priority_label': priority_labels.get(task.priority),
                'department': task.department_id.name or '',
                'user': task.user_id.name or '',
                'steps': task.check_progress,
                'deadline': task.date_deadline and fields.Datetime.to_string(task.date_deadline) or False,
                'overdue': bool(task.state != 'done' and task.date_deadline and task.date_deadline < now),
                'state': task.state,
                'linked': linked and linked.display_name or '',
            })
        return values

    # ------------------------------------------------------------------
    # Reminders (cron)
    # ------------------------------------------------------------------

    @api.model
    def _cron_send_due_reminders(self):
        """ Remind assignees in Discuss when a task falls due within 15 minutes. """
        soon = fields.Datetime.now() + timedelta(minutes=15)
        tasks = self.search([
            ('state', '!=', 'done'), ('reminder_sent', '=', False),
            ('date_deadline', '!=', False), ('date_deadline', '<=', soon), ('user_id', '!=', False),
        ])
        for task in tasks:
            task.message_post(
                body=_('Reminder: "%(task)s" is due.', task=task.name),
                partner_ids=task.user_id.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )
        tasks.write({'reminder_sent': True})


class TaskhubTaskCheck(models.Model):
    _name = 'taskhub.task.check'
    _description = 'Task Hub Checklist Item'
    _order = 'sequence, id'

    task_id = fields.Many2one('taskhub.task', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Step', required=True)
    status = fields.Selection(
        [('pending', 'Pending'), ('working', 'Working'), ('completed', 'Completed')],
        default='pending', required=True)
    quantity = fields.Char()
    supplier = fields.Char()
    link = fields.Char()
    note = fields.Char()

    def action_toggle(self):
        for check in self:
            check.status = 'pending' if check.status == 'completed' else 'completed'
