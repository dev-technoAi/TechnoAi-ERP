import base64
import csv
import io
import json
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round, format_amount

# header words, best match first; a header is compared in lower case with spaces squeezed
NAME_HEADERS = ('description', 'item description', 'product description', 'item', 'items', 'product', 'product name',
                'particulars', 'material', 'name')
QTY_HEADERS = ('qty', 'quantity', 'qnty', 'qty.', 'quantity required', 'req qty', 'pcs', 'nos', 'units', 'unit')
# selling price: a margin / selling column wins over a plain "price" (which in a costing sheet is the cost)
SELL_HEADERS = (('margin', 'sell', 'selling', 'sale price', 'offer price', 'quoted price'),
                ('unit price', 'unit rate', 'rate'),
                ('price',))
LEAD_HEADERS = ('lead time', 'leadtime', 'delivery time', 'lead')
NOT_SELL = ('total', 'cost', 'amount')
SKIP_NAMES = ('total', 'sub total', 'subtotal', 'grand total', 'vat', 'tax', 'net total')


def _clean(value):
    return re.sub(r'\s+', ' ', str(value if value is not None else '').replace('\xa0', ' ')).strip()


def _number(value):
    if isinstance(value, bool) or value in (None, ''):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r'-?\d[\d,]*(\.\d+)?', str(value))
    return float(match.group(0).replace(',', '')) if match else None


def _read_rows(env, content, filename):
    """ The sheet as a list of rows (lists of cell values): .xlsx, .xls or .csv. """
    name = (filename or '').lower()
    if name.endswith('.csv'):
        text = content.decode('utf-8-sig', errors='replace')
        return [row for row in csv.reader(io.StringIO(text))]
    if name.endswith('.xls'):
        import xlrd
        sheet = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
        return [sheet.row_values(i) for i in range(sheet.nrows)]
    import openpyxl
    try:
        book = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as error:
        raise UserError(env._('This file could not be read as an Excel sheet (%s).', error)) from error
    sheet = book.worksheets[0]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def _find_columns(header):
    """ {'name': i, 'quantity': i, 'price': i, 'lead': i} from a header row; missing keys are left out. """
    labels = [_clean(cell).lower() for cell in header]
    found = {}

    def first(words, exact=False, skip=()):
        for word in words:
            for i, label in enumerate(labels):
                if not label or i in found.values() or any(bad in label for bad in skip):
                    continue
                if label == word or (not exact and word in label):
                    return i
        return None

    name = first(NAME_HEADERS)
    if name is not None:
        found['name'] = name
    qty = first(QTY_HEADERS, exact=True)
    if qty is not None:
        found['quantity'] = qty
    for group in SELL_HEADERS:
        price = first(group, skip=NOT_SELL if group != SELL_HEADERS[0] else ('total',))
        if price is not None:
            found['price'] = price
            break
    lead = first(LEAD_HEADERS)
    if lead is not None:
        found['lead'] = lead
    return found, labels


def parse_sheet(env, content, filename):
    """ The items of a quotation sheet: [{'name', 'quantity', 'price', 'lead'}], and how the columns were read. """
    rows = _read_rows(env, content, filename)
    for index, row in enumerate(rows[:15]):
        columns, labels = _find_columns(row)
        if 'name' in columns and ('price' in columns or 'quantity' in columns):
            break
    else:
        raise UserError(env._('No header row with an item (description) column and a price or quantity column was found '
                          'in the first 15 rows of the sheet.'))
    items = []
    for row in rows[index + 1:]:
        cell = lambda key: row[columns[key]] if key in columns and columns[key] < len(row) else None
        name = _clean(cell('name'))
        if not name or name.lower().strip(' :') in SKIP_NAMES:
            continue
        quantity = _number(cell('quantity'))
        price = _number(cell('price'))
        if quantity is None and price is None:
            continue  # a note or a section title, not an item
        items.append({
            'name': name,
            'quantity': quantity if quantity else 1.0,
            'price': price or 0.0,
            'lead': _clean(cell('lead')),
        })
    used = {key: labels[i] for key, i in columns.items()}
    return items, used


class SaleExcelImport(models.TransientModel):
    _name = 'sale.excel.import'
    _description = 'Sales Order from Excel'

    partner_id = fields.Many2one('res.partner', 'Customer', required=True)
    # kept in the record itself, and always read as content (the web client asks binaries as sizes)
    file = fields.Binary('Excel file', required=True, attachment=False)
    filename = fields.Char()
    vat = fields.Selection([('5', '5% (default)'), ('0', '0%')], 'VAT', default='5', required=True)
    items_json = fields.Text(compute='_compute_items', store=True)
    columns_json = fields.Text(compute='_compute_items', store=True)
    parse_error = fields.Char(compute='_compute_items', store=True)
    item_count = fields.Integer(compute='_compute_items', store=True)
    preview_html = fields.Html(compute='_compute_preview', sanitize=False)

    @api.depends('file', 'filename')
    def _compute_items(self):
        for wizard in self.with_context(bin_size=False):
            items, used, error = [], {}, False
            if wizard.file:
                try:
                    items, used = parse_sheet(wizard.env, base64.b64decode(wizard.file), wizard.filename)
                    if not items:
                        error = _('No items were found under the header row of the sheet.')
                except UserError as exc:
                    error = exc.args[0]
                except Exception as exc:  # a broken file must not break the dialog
                    error = _('This file could not be read (%s).', exc)
            wizard.items_json = json.dumps(items)
            wizard.columns_json = json.dumps(used)
            wizard.parse_error = error
            wizard.item_count = len(items)

    def _currency(self):
        pricelist = self.partner_id.property_product_pricelist
        return pricelist.currency_id or self.env.company.currency_id

    def _lines(self):
        """ The items with the unit price rounded as the order will round it. """
        digits = self.env['decimal.precision'].precision_get('Product Price')
        items = json.loads(self.items_json or '[]')
        for item in items:
            item['price'] = float_round(item['price'], precision_digits=digits)
        return items

    @api.depends('items_json', 'parse_error', 'vat', 'partner_id')
    def _compute_preview(self):
        for wizard in self:
            if not wizard.file:
                wizard.preview_html = Markup('<p class="text-muted mb-0">%s</p>') % _('Choose the Excel file to see its items here.')
                continue
            if wizard.parse_error:
                wizard.preview_html = Markup('<div class="alert alert-danger mb-0">%s</div>') % wizard.parse_error
                continue
            currency = wizard._currency()
            amount = lambda value: format_amount(wizard.env, value, currency)
            rows = []
            untaxed = tax = 0.0
            rate = float(wizard.vat or 0)
            for number, item in enumerate(wizard._lines(), 1):
                subtotal = currency.round(item['price'] * item['quantity'])
                untaxed += subtotal
                tax += currency.round(subtotal * rate / 100)  # VAT rounded per line, as on the order
                lead = Markup('<div class="text-muted small">%s</div>') % _('Lead time: %s', item['lead']) if item['lead'] else ''
                rows.append(Markup(
                    '<tr><td>%s</td><td>%s%s</td><td class="text-end">%s</td><td class="text-end">%s</td><td class="text-end">%s</td></tr>'
                ) % (number, item['name'], lead, ('%g' % item['quantity']), amount(item['price']), amount(subtotal)))
            used = json.loads(wizard.columns_json or '{}')
            labels = {'name': _('Item'), 'quantity': _('Quantity'), 'price': _('Unit price'), 'lead': _('a line under each item')}
            read = ', '.join('%s → %s' % (used[key], labels[key]) for key in ('name', 'quantity', 'price', 'lead') if key in used)
            wizard.preview_html = Markup(
                '<div class="o_sale_excel_preview">'
                '<div class="text-uppercase small fw-bold text-muted mb-2">%(title)s</div>'
                '<div class="border-bottom mb-2" style="max-height:46vh;overflow:auto"><table class="table table-sm align-middle mb-0">'
                '<thead><tr><th>#</th><th>%(item)s</th><th class="text-end">%(qty)s</th><th class="text-end">%(price)s</th>'
                '<th class="text-end">%(amount)s</th></tr></thead><tbody>%(rows)s</tbody></table></div>'
                '<div class="d-flex justify-content-end gap-4 mb-2">'
                '<span>%(untaxed_l)s <b>%(untaxed)s</b></span><span>%(vat_l)s <b>%(tax)s</b></span>'
                '<span>%(total_l)s <b>%(total)s</b></span></div>'
                '<div class="alert alert-info small mb-0"><b>%(read_l)s</b> %(read)s. %(private)s</div></div>'
            ) % {
                'title': _('Items that will go on the Sales Order'),
                'item': _('Item'), 'qty': _('Quantity'), 'price': _('Unit price'), 'amount': _('Amount'),
                'rows': Markup('').join(rows),
                'untaxed_l': _('Untaxed'), 'untaxed': amount(untaxed),
                'vat_l': _('VAT %s%%', wizard.vat), 'tax': amount(tax),
                'total_l': _('Total'), 'total': amount(untaxed + tax),
                'read_l': _('Read from the sheet:'), 'read': read,
                'private': _('The other columns (cost, supplier, links, delivery, contact) stay private: they are not put on the order.'),
            }

    def _taxes(self):
        """ The company's sales tax for the chosen rate; none for 0% when the company has no 0% sales tax. """
        company = self.env.company
        rate = float(self.vat or 0)
        default = company.account_sale_tax_id
        if default.amount_type == 'percent' and default.amount == rate and not default.price_include:
            return default
        taxes = self.env['account.tax'].search([
            *self.env['account.tax']._check_company_domain(company),
            ('type_tax_use', '=', 'sale'), ('amount_type', '=', 'percent'), ('amount', '=', rate),
        ]).filtered(lambda t: not t.price_include and not any(
            word in (t.name or '').lower() for word in ('reverse', 'tourist', 'refund', 'exempt')))
        if not taxes and rate:
            raise UserError(_('No %s%% sales tax was found. Add one in Invoicing > Configuration > Taxes.', self.vat))
        return taxes[:1]

    def action_create(self):
        self.ensure_one()
        if self.parse_error:
            raise UserError(self.parse_error)
        lines = self._lines()
        if not lines:
            raise UserError(_('The sheet has no items.'))
        taxes = self._taxes()
        fallback = self.env.ref('technoai_taskhub.product_quoted_item')
        catalog = self.env['taskhub.quotation']
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'order_line': [(0, 0, {
                'product_id': (catalog._catalog_product(item['name']) or fallback).id,
                'name': item['name'] + ('\n' + _('Lead time: %s', item['lead']) if item['lead'] else ''),
                'product_uom_qty': item['quantity'],
                'price_unit': item['price'],
                'tax_id': [(6, 0, taxes.ids)],
            }) for item in lines],
        })
        # the sheet (with its costs and suppliers) stays an internal note, never sent to the customer
        attachment = self.env['ir.attachment'].create({
            'name': self.filename or 'quotation.xlsx', 'datas': self.with_context(bin_size=False).file, 'res_model': order._name, 'res_id': order.id,
        })
        # logged (not posted): an internal note that notifies nobody and works for users without an email address
        order._message_log(
            body=_('Quotation created from Excel file %(file)s (%(count)s lines).', file=self.filename or '', count=len(lines)),
            attachment_ids=attachment.ids, message_type='comment')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }
