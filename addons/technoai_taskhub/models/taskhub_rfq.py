import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, parse_contact_from_email

RFQ_STATES = [
    ('new', 'New'),
    ('approved', 'Approved'),
    ('quoted', 'Quote sent'),
    ('negotiating', 'Negotiating'),
    ('won', 'Won'),
    ('lost', 'Lost'),
    ('rejected', 'Rejected'),
]
OPEN_STATES = ('new', 'approved', 'quoted', 'negotiating')

# "3 x Rugged laptop", "3 pcs Rugged laptop", "- Rugged laptop x 3", "Rugged laptop - qty 3"
ITEM_PATTERNS = [
    re.compile(r'^\s*(?:[-*•]\s*)?(\d+(?:\.\d+)?)\s*(?:x|×|pcs?|units?|nos?|ea)\.?\s+(.{3,})$', re.I),
    re.compile(r'^\s*(?:[-*•]\s*)?(.{3,}?)\s*(?:[-:,]\s*)?(?:x|×|qty:?|quantity:?)\s*(\d+(?:\.\d+)?)\s*(?:pcs?|units?|nos?|ea)?\.?\s*$', re.I),
]


class TaskhubRfq(models.Model):
    _name = 'taskhub.rfq'
    _description = 'Email RFQ'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_received desc, id desc'

    name = fields.Char('RFQ', required=True, readonly=True, copy=False, default=lambda self: _('New'))
    subject = fields.Char(required=True, tracking=True)
    state = fields.Selection(RFQ_STATES, default='new', required=True, tracking=True, group_expand='_read_group_state')
    is_open = fields.Boolean(compute='_compute_is_open', search='_search_is_open')
    partner_id = fields.Many2one('res.partner', 'Client', tracking=True)
    client_name = fields.Char()
    client_email = fields.Char(tracking=True)
    client_phone = fields.Char()
    date_received = fields.Datetime('Received', default=fields.Datetime.now)
    source = fields.Selection([('email', 'Email'), ('manual', 'Manual')], default='manual', readonly=True)
    email_body = fields.Html('Email', sanitize_style=True)
    line_ids = fields.One2many('taskhub.rfq.line', 'rfq_id', 'Requested items', copy=True)
    user_id = fields.Many2one('res.users', 'Assigned to', tracking=True, domain=[('share', '=', False)])
    department_id = fields.Many2one('hr.department', 'Department',
                                    default=lambda self: self.env.ref('technoai_taskhub.dept_procurement', raise_if_not_found=False))
    task_id = fields.Many2one('taskhub.task', 'Task', readonly=True, copy=False)
    quotation_ids = fields.One2many('taskhub.quotation', 'rfq_id', 'Quotations')
    quotation_count = fields.Integer(compute='_compute_quotation_count')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary('Value', tracking=True, help='Quoted value; the final contract value once won.')
    date_quoted = fields.Datetime('Quote sent on', readonly=True)
    date_closed = fields.Datetime('Closed on', readonly=True, help='When the RFQ was won, lost or rejected.')
    reason = fields.Text('Win / loss / rejection reason', tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    color = fields.Integer()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('taskhub.rfq') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if 'state' in vals:
            closed = vals['state'] in ('won', 'lost', 'rejected')
            vals = dict(vals, date_closed=fields.Datetime.now() if closed else False)
        return super().write(vals)

    def _read_group_state(self, states, domain):
        return [key for key, _label in RFQ_STATES if key != 'rejected']

    @api.depends('state')
    def _compute_is_open(self):
        for rfq in self:
            rfq.is_open = rfq.state in OPEN_STATES

    def _search_is_open(self, operator, value):
        positive = (operator == '=') == bool(value)
        return [('state', 'in' if positive else 'not in', OPEN_STATES)]

    def _compute_quotation_count(self):
        for rfq in self:
            rfq.quotation_count = len(rfq.quotation_ids)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.client_name = self.partner_id.name
            self.client_email = self.partner_id.email or self.client_email
            self.client_phone = self.partner_id.phone or self.partner_id.mobile or self.client_phone

    # ------------------------------------------------------------------
    # Email intake: emails sent to the RFQ alias become RFQs
    # ------------------------------------------------------------------

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        name, email = parse_contact_from_email(msg_dict.get('email_from') or '')
        partner = self.env['res.partner'].search([('email', '=ilike', email)], limit=1) if email else self.env['res.partner']
        body = msg_dict.get('body') or ''
        values = dict(custom_values or {}, **{
            # keeps mail.thread from using the subject as the name, so the RFQ gets its number
            'name': _('New'),
            'subject': msg_dict.get('subject') or _('RFQ from %s', name or email or _('unknown sender')),
            'client_name': partner.name or name,
            'client_email': email,
            'partner_id': partner.id,
            'email_body': body,
            'source': 'email',
            'line_ids': [(0, 0, item) for item in self._parse_items(html2plaintext(body))],
        })
        return super().message_new(msg_dict, custom_values=values)

    @api.model
    def _parse_items(self, text):
        """ Best-effort list of requested items ("3 x laptop", "laptop x 3") from an email body. """
        items = []
        for line in (text or '').splitlines():
            line = line.strip()
            if not line or len(line) > 160:
                continue
            for pattern in ITEM_PATTERNS:
                match = pattern.match(line)
                if not match:
                    continue
                first, second = match.groups()
                qty, name = (first, second) if pattern is ITEM_PATTERNS[0] else (second, first)
                items.append({'name': name.strip(' .:-'), 'quantity': float(qty)})
                break
        return items[:50]

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _check_taskhub_admin(self):
        if not self.env.user.has_group('technoai_taskhub.group_taskhub_admin'):
            raise UserError(_('Only Task Hub administrators can approve or reject RFQs.'))

    def action_approve(self):
        """ Approve the RFQ and create the Task Hub task that tracks it. """
        self._check_taskhub_admin()
        for rfq in self:
            if not rfq.user_id:
                raise UserError(_('Assign %s to someone before approving it.', rfq.name))
            if not rfq.task_id:
                rfq.task_id = self.env['taskhub.task'].create({
                    'name': _('Prepare quotation: %(subject)s', subject=rfq.subject),
                    'priority': 'high',
                    'user_id': rfq.user_id.id,
                    'department_id': rfq.department_id.id,
                    'partner_id': rfq.partner_id.id,
                    'linked_ref': '%s,%s' % (rfq._name, rfq.id),
                    'description': rfq.email_body,
                    'check_ids': [(0, 0, {'name': _('Review the request and attachments'), 'sequence': 1})]
                                 + [(0, 0, {'name': line.name, 'quantity': line.quantity_display, 'sequence': 10 + i})
                                    for i, line in enumerate(rfq.line_ids)]
                                 + [(0, 0, {'name': _('Prepare and send the quotation'), 'sequence': 900})],
                })
            rfq.state = 'approved'
        return True

    def action_reject(self):
        self._check_taskhub_admin()
        self.write({'state': 'rejected'})

    def action_mark_quoted(self):
        self.write({'state': 'quoted', 'date_quoted': fields.Datetime.now()})

    def action_negotiating(self):
        self.write({'state': 'negotiating'})

    def action_won(self):
        self.write({'state': 'won'})
        # what was bought for a won deal becomes confirmed sourcing history
        self.env['taskhub.sourcing'].search([('rfq_id', 'in', self.ids), ('status', 'in', ('quoted', 'unconfirmed'))]).write({'status': 'confirmed'})
        self.task_id.filtered(lambda t: t.state != 'done').action_mark_done()

    def action_lost(self):
        self.write({'state': 'lost'})

    def action_reopen(self):
        self.write({'state': 'new' if not self.task_id else 'approved'})

    def action_new_quotation(self):
        """ Open a draft quotation prefilled from the RFQ items. """
        self.ensure_one()
        quotation = self.quotation_ids[:1] or self.env['taskhub.quotation'].create({
            'rfq_id': self.id,
            'partner_id': self.partner_id.id,
            'client_name': self.partner_id.name or self.client_name,
            'client_email': self.client_email,
            'line_ids': [(0, 0, {'name': line.name, 'quantity': line.quantity or 1.0, 'uom': line.uom or _('Unit')})
                         for line in self.line_ids],
        })
        return quotation._open_form()

    def action_open_quotations(self):
        self.ensure_one()
        if len(self.quotation_ids) == 1:
            return self.quotation_ids._open_form()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quotations'),
            'res_model': 'taskhub.quotation',
            'view_mode': 'list,form',
            'domain': [('rfq_id', '=', self.id)],
        }

    def action_open_sourcing(self):
        """ Past prices and suppliers for the requested items. """
        self.ensure_one()
        words = [line.name.split()[0] for line in self.line_ids if line.name]
        domain = []
        for word in words[:5]:
            domain = ['|', ('name', 'ilike', word)] + domain if domain else [('name', 'ilike', word)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sourcing for %s', self.name),
            'res_model': 'taskhub.sourcing',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_fetch_emails(self):
        """ Check the incoming mail servers now instead of waiting for the next run. """
        servers = self.env['fetchmail.server'].sudo().search([('state', '=', 'done')])
        if not servers:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'warning',
                    'title': _('Email is not set up yet'),
                    'message': _('Add an incoming mail server for the RFQ mailbox, then emails arrive here automatically.'),
                },
            }
        servers.fetch_mail()
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class TaskhubRfqLine(models.Model):
    _name = 'taskhub.rfq.line'
    _description = 'Email RFQ item'
    _order = 'sequence, id'

    rfq_id = fields.Many2one('taskhub.rfq', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Item', required=True)
    quantity = fields.Float(default=1.0)
    uom = fields.Char('Unit')
    note = fields.Char('Specifications')
    quantity_display = fields.Char(compute='_compute_quantity_display')

    @api.depends('quantity', 'uom')
    def _compute_quantity_display(self):
        for line in self:
            qty = ('%g' % line.quantity) if line.quantity else ''
            line.quantity_display = ' '.join(filter(None, [qty and '%s x' % qty, line.uom]))
