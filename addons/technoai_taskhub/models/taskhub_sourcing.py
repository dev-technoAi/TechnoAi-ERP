import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.osv import expression

# prices older than this get an "Old price" tag on quotations
OLD_PRICE_DAYS = 180
IGNORED_WORDS = {'a', 'an', 'and', 'for', 'of', 'the', 'with', 'x', 'pc', 'pcs', 'unit', 'units', 'new'}

SOURCING_STATES = [
    ('inquired', 'Inquired'),
    ('quoted', 'Quoted'),
    ('unconfirmed', 'Unconfirmed'),
    ('confirmed', 'Confirmed order'),
]


def _item_words(text):
    """ "24-Port Network Switch" -> {'24', 'port', 'network', 'switch'} """
    return set(re.findall(r'[a-z0-9]+', (text or '').lower())) - IGNORED_WORDS


class TaskhubSourcing(models.Model):
    """ Products and prices found while sourcing, kept even when the deal is lost. """
    _name = 'taskhub.sourcing'
    _description = 'Sourcing record'
    _order = 'write_date desc, id desc'

    name = fields.Char('Product', required=True)
    part_number = fields.Char()
    specifications = fields.Text()
    supplier_id = fields.Many2one('res.partner', 'Supplier', index=True)
    url = fields.Char('Product link')
    unit_cost = fields.Monetary('Unit cost')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    rfq_id = fields.Many2one('taskhub.rfq', 'RFQ', ondelete='set null')
    client_id = fields.Many2one('res.partner', 'Client')
    status = fields.Selection(SOURCING_STATES, default='inquired', required=True)
    status_rank = fields.Integer(compute='_compute_status_rank', store=True)
    notes = fields.Text()
    source_key = fields.Char(index=True, copy=False, help='Line this record was created from, so it is updated instead of duplicated.')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    # tags of the Known suppliers list on draft quotations
    best_label = fields.Char('Price', compute='_compute_price_labels')
    old_label = fields.Char('Price age', compute='_compute_price_labels')

    @api.depends('write_date')
    def _compute_price_labels(self):
        limit = fields.Datetime.now() - timedelta(days=OLD_PRICE_DAYS)
        for record in self:
            record.best_label = _('Best price')
            record.old_label = _('Old price') if record.write_date and record.write_date < limit else False

    def _cost_in(self, currency):
        self.ensure_one()
        if not currency or currency == self.currency_id:
            return self.unit_cost
        return self.currency_id._convert(self.unit_cost, currency, self.company_id or self.env.company, fields.Date.context_today(self))

    @api.model
    def _known_for_item(self, name, currency=None):
        """ The suppliers we already have a price from for this item, cheapest first:
        each supplier once, with their most recent price. """
        words = _item_words(name)
        if not words:
            return self.browse()
        domain = expression.OR([['|', ('name', 'ilike', word), ('part_number', 'ilike', word)] for word in words])
        domain = expression.AND([domain, [('unit_cost', '>', 0), ('supplier_id', '!=', False)]])
        known = {}
        for record in self.search(domain, order='write_date desc, id desc', limit=500):
            if record.supplier_id not in known and record._matches_item(words):
                known[record.supplier_id] = record
        return self.browse([r.id for r in sorted(known.values(), key=lambda r: r._cost_in(currency))])

    def _matches_item(self, words):
        """ Same part number or same name, or most words in common ("24 Port Switch" and "24-Port Network Switch"). """
        self.ensure_one()
        part = _item_words(self.part_number)
        if part and part <= words:
            return True
        theirs = _item_words(self.name)
        if theirs == words:
            return True
        shared = theirs & words
        return len(shared) >= 2 and len(shared) / min(len(theirs), len(words)) >= 0.75

    def action_use_for_line(self):
        """ Use this supplier and price on the quotation line in the context. """
        self.ensure_one()
        line = self.env['taskhub.quotation.line'].browse(self.env.context.get('taskhub_line_id') or []).exists()
        if line:
            line.write({
                'supplier_id': self.supplier_id.id,
                'cost': self._cost_in(line.currency_id),
                'source_url': self.url or line.source_url,
            })
        return True

    @api.depends('status')
    def _compute_status_rank(self):
        ranks = {key: rank for rank, (key, _label) in enumerate(SOURCING_STATES)}
        for record in self:
            record.status_rank = ranks.get(record.status, 0)
