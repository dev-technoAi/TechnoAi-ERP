from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TaskhubQuotation(models.Model):
    _name = 'taskhub.quotation'
    _description = 'Draft Quotation'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Quotation', required=True, readonly=True, copy=False, default=lambda self: _('New'))
    rfq_id = fields.Many2one('taskhub.rfq', 'RFQ', ondelete='set null', index=True)
    partner_id = fields.Many2one('res.partner', 'Client', tracking=True)
    client_name = fields.Char('Client name')
    client_email = fields.Char('Contact email')
    date = fields.Date(default=fields.Date.context_today)
    valid_until = fields.Date(default=lambda self: fields.Date.context_today(self) + timedelta(days=15))
    vat_rate = fields.Float('VAT %', default=5.0)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', 'Prepared by', default=lambda self: self.env.user)
    line_ids = fields.One2many('taskhub.quotation.line', 'quotation_id', 'Lines', copy=True)
    amount_untaxed = fields.Monetary('Untaxed', compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary('VAT', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary('Total', compute='_compute_amounts', store=True)
    amount_cost = fields.Monetary('Cost', compute='_compute_amounts', store=True)
    margin_percent = fields.Float('Margin %', compute='_compute_amounts', store=True, digits=(16, 1))
    notes = fields.Html('Terms & notes')
    state = fields.Selection([('draft', 'Draft'), ('sent', 'Sent')], default='draft', tracking=True)
    sale_order_id = fields.Many2one('sale.order', 'Sales quotation', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('taskhub.quotation') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.subtotal', 'line_ids.cost_subtotal', 'vat_rate')
    def _compute_amounts(self):
        for quote in self:
            untaxed = sum(quote.line_ids.mapped('subtotal'))
            cost = sum(quote.line_ids.mapped('cost_subtotal'))
            quote.amount_untaxed = untaxed
            quote.amount_tax = quote.currency_id.round(untaxed * quote.vat_rate / 100.0)
            quote.amount_total = untaxed + quote.amount_tax
            quote.amount_cost = cost
            quote.margin_percent = (untaxed - cost) / untaxed * 100.0 if untaxed else 0.0

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.client_name = self.partner_id.name
            self.client_email = self.partner_id.email or self.client_email

    def _open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'taskhub.quotation',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Outputs: PDF, Excel, email, Sales
    # ------------------------------------------------------------------

    def action_print_pdf(self):
        return self.env.ref('technoai_taskhub.action_report_taskhub_quotation').report_action(self)

    def action_download_excel(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/taskhub/quotation/%s/xlsx' % self.id, 'target': 'self'}

    def action_send_email(self):
        """ Email the PDF to the client; sending marks the quotation and its RFQ as quoted. """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Add at least one line before sending the quotation.'))
        self._index_sourcing('quoted')
        template = self.env.ref('technoai_taskhub.mail_template_taskhub_quotation')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_model': self._name,
                'default_res_ids': self.ids,
                'default_template_id': template.id,
                'default_composition_mode': 'comment',
                'default_email_layout_xmlid': 'mail.mail_notification_light',
                'mark_taskhub_quotation_sent': True,
                'force_email': True,
            },
        }

    def message_post(self, **kwargs):
        if self.env.context.get('mark_taskhub_quotation_sent'):
            for quote in self.filtered(lambda q: q.state == 'draft'):
                quote.state = 'sent'
            rfqs = self.rfq_id.filtered(lambda r: r.state in ('new', 'approved'))
            rfqs.write({'state': 'quoted', 'date_quoted': fields.Datetime.now()})
            for quote in self.filtered('rfq_id'):
                if not quote.rfq_id.amount:
                    quote.rfq_id.amount = quote.amount_total
        return super(TaskhubQuotation, self.with_context(mark_taskhub_quotation_sent=False)).message_post(**kwargs)

    def action_create_sale_order(self):
        """ Turn the draft quotation into a quotation of the Sales app. """
        self.ensure_one()
        if self.sale_order_id:
            return self._open_sale_order()
        if not self.partner_id:
            raise UserError(_('Choose the client (a contact) before creating the Sales quotation.'))
        product = self.env.ref('technoai_taskhub.product_quoted_item')
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'validity_date': self.valid_until,
            'origin': ' / '.join(filter(None, [self.name, self.rfq_id.name])),
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': line.name,
                'product_uom_qty': line.quantity,
                'price_unit': line.price_unit,
                'tax_id': [(6, 0, [])],
            }) for line in self.line_ids],
        })
        self.sale_order_id = order
        self.message_post(body=_('Sales quotation %s created.', order._get_html_link()))
        if self.rfq_id.task_id:
            self.rfq_id.task_id.linked_ref = '%s,%s' % (order._name, order.id)
        return self._open_sale_order()

    def _open_sale_order(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _index_sourcing(self, status):
        """ Keep every quoted price as sourcing history, so the next RFQ can reuse it. """
        Sourcing = self.env['taskhub.sourcing']
        for line in self.line_ids.filtered(lambda l: l.supplier_id or l.source_url):
            key = 'quotation-line-%s' % line.id
            values = {
                'name': line.name,
                'supplier_id': line.supplier_id.id,
                'url': line.source_url,
                'unit_cost': line.cost,
                'currency_id': self.currency_id.id,
                'rfq_id': self.rfq_id.id,
                'client_id': self.partner_id.id,
                'status': status,
                'source_key': key,
            }
            existing = Sourcing.search([('source_key', '=', key)], limit=1)
            if existing:
                existing.write(values)
            else:
                Sourcing.create(values)


class TaskhubQuotationLine(models.Model):
    _name = 'taskhub.quotation.line'
    _description = 'Draft Quotation line'
    _order = 'sequence, id'

    quotation_id = fields.Many2one('taskhub.quotation', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='quotation_id.currency_id')
    sequence = fields.Integer(default=10)
    name = fields.Char('Item', required=True)
    supplier_id = fields.Many2one('res.partner', 'Supplier')
    source_url = fields.Char('Source link')
    quantity = fields.Float(default=1.0)
    uom = fields.Char('UoM', default=lambda self: _('Unit'))
    cost = fields.Monetary('Cost')
    price_unit = fields.Monetary('Unit price')
    subtotal = fields.Monetary('Amount', compute='_compute_subtotal', store=True)
    cost_subtotal = fields.Monetary(compute='_compute_subtotal', store=True)

    @api.depends('quantity', 'price_unit', 'cost')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit
            line.cost_subtotal = line.quantity * line.cost

    @api.onchange('name', 'supplier_id')
    def _onchange_suggest_cost(self):
        """ Suggest the last known cost of the item from the sourcing history. """
        if not self.name or self.cost:
            return
        domain = [('name', 'ilike', self.name), ('unit_cost', '>', 0)]
        if self.supplier_id:
            domain.append(('supplier_id', '=', self.supplier_id.id))
        record = self.env['taskhub.sourcing'].search(domain, limit=1, order='status_rank desc, write_date desc')
        if record:
            self.cost = record.unit_cost
            self.supplier_id = self.supplier_id or record.supplier_id
            self.source_url = self.source_url or record.url
