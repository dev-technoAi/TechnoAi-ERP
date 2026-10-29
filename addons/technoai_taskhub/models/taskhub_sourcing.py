from odoo import api, fields, models

SOURCING_STATES = [
    ('inquired', 'Inquired'),
    ('quoted', 'Quoted'),
    ('unconfirmed', 'Unconfirmed'),
    ('confirmed', 'Confirmed order'),
]


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

    @api.depends('status')
    def _compute_status_rank(self):
        ranks = {key: rank for rank, (key, _label) in enumerate(SOURCING_STATES)}
        for record in self:
            record.status_rank = ranks.get(record.status, 0)
