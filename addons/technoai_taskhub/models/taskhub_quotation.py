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
    purchase_order_ids = fields.Many2many('purchase.order', string='Purchase Orders', readonly=True, copy=False)
    purchase_count = fields.Integer(compute='_compute_purchase_count')
    revision_of_id = fields.Many2one('taskhub.quotation', 'Revision of', readonly=True, copy=False, ondelete='set null')
    rfq_email_body = fields.Html(related='rfq_id.email_body', string='Client email')
    rfq_email_from = fields.Char(related='rfq_id.client_email', string='From')
    rfq_date_received = fields.Datetime(related='rfq_id.date_received', string='Received')
    online_result_ids = fields.One2many('taskhub.online.result', 'quotation_id', 'Online search results')
    online_item_name = fields.Char(compute='_compute_online_item_name')
    known_line_id = fields.Many2one('taskhub.quotation.line', 'Item chosen for Known suppliers', ondelete='set null', copy=False)
    known_current_line_id = fields.Many2one('taskhub.quotation.line', compute='_compute_known_suppliers')
    known_item_name = fields.Char(compute='_compute_known_suppliers')
    known_source_ids = fields.Many2many('taskhub.sourcing', string='Known suppliers', compute='_compute_known_suppliers')
    known_best_id = fields.Many2one('taskhub.sourcing', compute='_compute_known_suppliers')
    known_selected_id = fields.Many2one('taskhub.sourcing', compute='_compute_known_suppliers')

    @api.depends('known_line_id', 'line_ids.name', 'line_ids.supplier_id', 'line_ids.cost', 'currency_id')
    def _compute_known_suppliers(self):
        """ The list under the lines: the item that was picked, else the first with known suppliers. """
        for quote in self:
            line = quote.known_line_id or quote.line_ids.filtered('known_count')[:1]
            quote.known_current_line_id = line
            quote.known_item_name = line.name
            quote.known_source_ids = line.known_source_ids
            quote.known_best_id = line.known_source_ids[:1]
            quote.known_selected_id = line.known_source_ids.filtered(
                lambda r: r.supplier_id == line.supplier_id and r._cost_in(line.currency_id) == line.cost)[:1]

    @api.depends('purchase_order_ids')
    def _compute_purchase_count(self):
        for quote in self:
            quote.purchase_count = len(quote.purchase_order_ids)

    @api.depends('online_result_ids.item')
    def _compute_online_item_name(self):
        for quote in self:
            quote.online_item_name = quote.online_result_ids[:1].item

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
        taxes = self._company_taxes('sale')
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'validity_date': self.valid_until,
            'origin': ' / '.join(filter(None, [self.name, self.rfq_id.name])),
            'order_line': [(0, 0, {
                'product_id': self._catalog_product(line.name).id or product.id,
                'name': line.name,
                'product_uom_qty': line.quantity,
                'price_unit': line.price_unit,
                'tax_id': [(6, 0, taxes.ids)],
            }) for line in self.line_ids],
        })
        if 'purchase_price' in order.order_line._fields:
            # the buying price, so Sales shows the real margin (needs the Margins app)
            for so_line, line in zip(order.order_line, self.line_ids):
                so_line.purchase_price = line.cost
        self.sale_order_id = order
        self.message_post(body=_('Sales quotation %s created.', order._get_html_link()))
        if self.rfq_id.task_id:
            self.rfq_id.task_id.linked_ref = '%s,%s' % (order._name, order.id)
        return self._open_sale_order()

    def _catalog_product(self, name, purchase=False):
        """ The product of the catalog with exactly this name or internal reference, if there is one. """
        name = (name or '').strip()
        if not name:
            return self.env['product.product']
        return self.env['product.product'].search(
            [('purchase_ok' if purchase else 'sale_ok', '=', True), '|', ('default_code', '=ilike', name), ('name', '=ilike', name)], limit=1)

    def _company_taxes(self, use):
        """ The sales or purchase tax ('sale' / 'purchase') for the quotation's VAT %: the company's default
        tax when it has that rate, otherwise a plain tax with that rate (not reverse charge or tourist refund). """
        self.ensure_one()
        if not self.vat_rate:
            return self.env['account.tax']
        company = self.company_id or self.env.company
        default = company.account_sale_tax_id if use == 'sale' else company.account_purchase_tax_id
        if default.amount_type == 'percent' and default.amount == self.vat_rate:
            return default
        taxes = self.env['account.tax'].search([
            *self.env['account.tax']._check_company_domain(company),
            ('type_tax_use', '=', use), ('amount_type', '=', 'percent'), ('amount', '=', self.vat_rate),
        ]).filtered(lambda t: not t.price_include and not any(
            word in (t.name or '').lower() for word in ('reverse', 'tourist', 'refund')))
        if not taxes:
            kind = _('sales') if use == 'sale' else _('purchase')
            raise UserError(_('No %(kind)s tax of %(rate)s%% was found. Add one in Invoicing > Configuration > Taxes, '
                              'or change the VAT %% of %(quote)s.', kind=kind, rate=self.vat_rate, quote=self.name))
        return taxes[:1]

    def action_create_purchase_orders(self):
        """ One draft Purchase Order per supplier of the lines, at each line's cost. """
        self.ensure_one()
        lines = self.line_ids.filtered('supplier_id')
        if not lines:
            raise UserError(_('Choose a supplier on the lines first.'))
        done = self.purchase_order_ids.filtered(lambda o: o.state != 'cancel').partner_id
        todo = lines.filtered(lambda l: l.supplier_id not in done)
        if not todo:
            return self.action_open_purchase_orders()
        fallback = self.env.ref('technoai_taskhub.product_sourced_item')
        taxes = self._company_taxes('purchase')
        orders = self.env['purchase.order']
        for supplier in todo.supplier_id:
            orders |= self.env['purchase.order'].create({
                'partner_id': supplier.id,
                'currency_id': self.currency_id.id,
                'origin': ' / '.join(filter(None, [self.name, self.rfq_id.name])),
                'order_line': [(0, 0, {
                    'product_id': (self._catalog_product(line.name, purchase=True) or fallback).id,
                    'name': line.name,
                    'product_qty': line.quantity,
                    'price_unit': line.cost,
                    'taxes_id': [(6, 0, taxes.ids)],
                }) for line in todo.filtered(lambda l: l.supplier_id == supplier)],
            })
        self.purchase_order_ids |= orders
        self.message_post(body=_('Purchase Orders created: %s', ', '.join(orders.mapped('name'))))
        return self.action_open_purchase_orders()

    def action_open_purchase_orders(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'domain': [('id', 'in', self.purchase_order_ids.ids)],
            'view_mode': 'list,form',
        }
        if len(self.purchase_order_ids) == 1:
            action.update(res_id=self.purchase_order_ids.id, view_mode='form')
        return action

    def action_new_revision(self):
        """ A copy of this quotation for a revised offer; the RFQ keeps every revision. """
        self.ensure_one()
        revision = self.copy({'state': 'draft', 'revision_of_id': self.id, 'known_line_id': False,
                              'date': fields.Date.context_today(self)})
        revision.message_post(body=_('Revision of %s.', self._get_html_link()))
        self.message_post(body=_('New revision: %s.', revision._get_html_link()))
        return revision._open_form()

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
    known_source_ids = fields.Many2many('taskhub.sourcing', compute='_compute_known_suppliers')
    known_count = fields.Integer(compute='_compute_known_suppliers')
    known_summary = fields.Char('Known suppliers', compute='_compute_known_suppliers')

    @api.depends('name', 'quotation_id.currency_id')
    def _compute_known_suppliers(self):
        Sourcing = self.env['taskhub.sourcing']
        for line in self:
            known = Sourcing._known_for_item(line.name, line.currency_id)
            line.known_source_ids = known
            line.known_count = len(known)
            if known:
                line.known_summary = _('%(count)s, from %(cost)s', count=len(known),
                                       cost='{:,.2f}'.format(known[0]._cost_in(line.currency_id)))
            else:
                line.known_summary = _('No supplier yet')

    def action_show_known_suppliers(self):
        self.ensure_one()
        self.quotation_id.known_line_id = self
        return True

    @api.depends('quantity', 'price_unit', 'cost')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit
            line.cost_subtotal = line.quantity * line.cost

    @api.onchange('name', 'supplier_id')
    def _onchange_suggest_cost(self):
        """ Suggest the best known price of the item from the sourcing history. """
        if not self.name or self.cost:
            return
        known = self.env['taskhub.sourcing']._known_for_item(self.name, self.currency_id)
        if self.supplier_id:
            known = known.filtered(lambda r: r.supplier_id == self.supplier_id)
        record = known[:1]
        if record:
            self.cost = record._cost_in(self.currency_id)
            self.supplier_id = self.supplier_id or record.supplier_id
            self.source_url = self.source_url or record.url
