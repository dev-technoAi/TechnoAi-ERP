import base64

from odoo import api, fields, models
from odoo.tools.misc import file_open

TAX_DISPLAY = [('excl', 'Tax Excl.'), ('incl', 'Tax Incl.')]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tai_remarks = fields.Text('Remarks', help='Copied to the delivery order when the order is confirmed.')
    tai_recurring_plan = fields.Selection(
        [('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('semi_annual', 'Semi-annual'), ('annual', 'Annual')],
        'Recurring Plan', help='For information only: it does not create invoices or renewals.')
    tai_availability = fields.Char('Availability', help='Shown on the quotation, for example "1-2 weeks".')
    tai_warranty = fields.Char('Warranty', help='Shown on the quotation, for example "Manufacturer Warranty".')
    tai_tax_display = fields.Selection(TAX_DISPLAY, 'Amounts', default='excl', required=True, copy=False)

    def _tai_letter_logo(self):
        """ The letter's logo, embedded so that printing never depends on fetching it over HTTP. """
        with file_open('technoai_sales_ext/static/src/img/letter_logo.png', 'rb') as logo:
            return 'data:image/png;base64,%s' % base64.b64encode(logo.read()).decode()

    @api.model
    def _technoai_ensure_pricelists(self):
        """ The Pricelist field needs at least one pricelist per company to choose from. """
        Pricelist = self.env['product.pricelist'].sudo()
        for company in self.env['res.company'].sudo().search([]):
            if not Pricelist.search_count([('company_id', 'in', (company.id, False)), ('currency_id', '=', company.currency_id.id)]):
                Pricelist.create({'name': 'Public Pricelist', 'currency_id': company.currency_id.id, 'company_id': company.id})
