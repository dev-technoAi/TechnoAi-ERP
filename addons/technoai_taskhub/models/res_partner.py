from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    taskhub_is_supplier = fields.Boolean('Task Hub supplier', help='Listed under Task Hub > Suppliers.')
    taskhub_supplier_category = fields.Char('Supplier category')
    taskhub_rating = fields.Selection(
        [('0', 'Not rated'), ('1', 'Poor'), ('2', 'Fair'), ('3', 'Good'), ('4', 'Very good'), ('5', 'Excellent')],
        'Rating', default='0')
    taskhub_payment_terms = fields.Char('Usual payment terms')
    taskhub_sourcing_ids = fields.One2many('taskhub.sourcing', 'supplier_id', 'Sourced products')
    taskhub_product_count = fields.Integer('Products', compute='_compute_taskhub_supplier_stats')
    taskhub_last_bought = fields.Date('Last bought', compute='_compute_taskhub_supplier_stats')
    taskhub_last_price = fields.Monetary('Last price', compute='_compute_taskhub_supplier_stats',
                                         currency_field='taskhub_currency_id')
    taskhub_currency_id = fields.Many2one('res.currency', compute='_compute_taskhub_supplier_stats')

    @api.depends('taskhub_sourcing_ids.status', 'taskhub_sourcing_ids.unit_cost')
    def _compute_taskhub_supplier_stats(self):
        for partner in self:
            records = partner.taskhub_sourcing_ids
            confirmed = records.filtered(lambda r: r.status == 'confirmed').sorted('write_date', reverse=True)[:1]
            partner.taskhub_product_count = len(records)
            partner.taskhub_last_bought = confirmed and confirmed.write_date.date() or False
            partner.taskhub_last_price = confirmed.unit_cost if confirmed else 0.0
            partner.taskhub_currency_id = confirmed.currency_id or self.env.company.currency_id
