import json
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'
DEFAULT_GEMINI_MODEL = 'gemini-3.6-flash'
SEARCH_PROMPT = """Search the web for suppliers, preferably in the UAE or the GCC, that sell this item:
"%(item)s"

Reply with only a JSON array, no other text, of up to 6 objects with these keys:
"supplier" (company name), "product" (the product name on their page), "price" (number, or null when no
price is shown), "currency" (ISO code such as AED or USD, or null), "url" (the product or supplier page).
Only include suppliers and pages that you found in the search results."""


class TaskhubOnlineResult(models.Model):
    """ A supplier found on the internet by the AI search; it only becomes sourcing history once saved. """
    _name = 'taskhub.online.result'
    _description = 'Online search result'
    _order = 'id'

    quotation_id = fields.Many2one('taskhub.quotation', required=True, ondelete='cascade', index=True)
    line_id = fields.Many2one('taskhub.quotation.line', ondelete='cascade')
    item = fields.Char('Searched item')
    supplier_name = fields.Char('Supplier')
    product_name = fields.Char('Product')
    price = fields.Float('Price seen')
    currency_code = fields.Char('Currency')
    url = fields.Char('Link')
    sourcing_id = fields.Many2one('taskhub.sourcing', 'Saved as', ondelete='set null')

    def action_save_to_suppliers(self):
        """ Keep this result as a supplier and a sourcing record, so Known suppliers lists it. """
        Partner = self.env['res.partner']
        for result in self.filtered(lambda r: not r.sourcing_id):
            name = (result.supplier_name or '').strip() or _('Unknown supplier')
            partner = Partner.search([('name', '=ilike', name), ('is_company', '=', True)], limit=1) \
                or Partner.search([('name', '=ilike', name)], limit=1) \
                or Partner.create({'name': name, 'is_company': True, 'website': result.url or False})
            currency = self.env['res.currency'].with_context(active_test=False).search(
                [('name', '=', (result.currency_code or '').upper())], limit=1) or result.quotation_id.currency_id
            result.sourcing_id = self.env['taskhub.sourcing'].create({
                'name': result.product_name or result.item,
                'supplier_id': partner.id,
                'url': result.url,
                'unit_cost': result.price,
                'currency_id': currency.id,
                'rfq_id': result.quotation_id.rfq_id.id,
                'status': 'inquired',
                'notes': _('Found online by the AI search; check the price and stock with the supplier.'),
            })
        return True


class TaskhubQuotationLine(models.Model):
    _inherit = 'taskhub.quotation.line'

    def action_search_online(self):
        """ Ask Gemini, with Google Search, for suppliers of this item; the results replace the last search. """
        self.ensure_one()
        if not self.name:
            raise UserError(_('Type the item first.'))
        rows = self._search_online(self.name)
        quote = self.quotation_id
        quote.online_result_ids.unlink()
        self.env['taskhub.online.result'].create([{
            'quotation_id': quote.id,
            'line_id': self.id,
            'item': self.name,
            'supplier_name': row.get('supplier'),
            'product_name': row.get('product'),
            'price': row.get('price') or 0.0,
            'currency_code': row.get('currency'),
            'url': row.get('url'),
        } for row in rows])
        if not rows:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'type': 'info', 'title': _('Online search'), 'message': _('No suppliers were found online for %s.', self.name),
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
            }
        return True

    @api.model
    def _search_online(self, item):
        params = self.env['ir.config_parameter'].sudo()
        key = params.get_param('technoai_ai.gemini_key')
        if not key:
            raise UserError(_('The online search uses Google Gemini. An administrator can add the Gemini API key in '
                              'Settings > Techno AI assistant.'))
        model = params.get_param('technoai_ai.gemini_model') or DEFAULT_GEMINI_MODEL
        try:
            response = requests.post(GEMINI_URL % model, timeout=120,
                                     headers={'x-goog-api-key': key, 'Content-Type': 'application/json'},
                                     json={'contents': [{'role': 'user', 'parts': [{'text': SEARCH_PROMPT % {'item': item}}]}],
                                           'tools': [{'google_search': {}}]})
        except requests.RequestException as error:
            raise UserError(_('Could not reach Google Gemini: %s', error)) from error
        if response.status_code == 429:
            raise UserError(_('Google did not allow the search. Searching Google from Gemini needs billing on the Gemini '
                              'API key (the free plan does not include it), or the limit for today is used up.'))
        if response.status_code >= 400:
            _logger.warning("Task Hub online search failed: %s %s", response.status_code, response.text[:300])
            raise UserError(_('Google Gemini returned an error (%s). Try again in a moment.', response.status_code))
        candidate = (response.json().get('candidates') or [{}])[0]
        text = ''.join(part.get('text', '') for part in (candidate.get('content') or {}).get('parts', []) if not part.get('thought'))
        return self._parse_online_rows(text)

    @api.model
    def _parse_online_rows(self, text):
        """ The JSON array in the model's reply, keeping only rows that name a supplier. """
        match = re.search(r'\[.*\]', text or '', re.S)
        if not match:
            return []
        try:
            rows = json.loads(match.group(0))
        except ValueError:
            return []
        clean = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not row.get('supplier'):
                continue
            price = row.get('price')
            if isinstance(price, str):
                number = re.search(r'\d+(?:\.\d+)?', price.replace(',', ''))
                price = float(number.group(0)) if number else None
            url = row.get('url') if isinstance(row.get('url'), str) and row['url'].startswith('http') else False
            clean.append({
                'supplier': str(row['supplier'])[:200],
                'product': str(row.get('product') or '')[:300],
                'price': float(price) if isinstance(price, (int, float)) else 0.0,
                'currency': (str(row['currency'])[:3].upper() if row.get('currency') else False),
                'url': url,
            })
        return clean[:6]
