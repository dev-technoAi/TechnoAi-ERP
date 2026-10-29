import io

import xlsxwriter

from odoo import http
from odoo.http import content_disposition, request


class TaskhubQuotationExport(http.Controller):

    @http.route('/taskhub/quotation/<int:quotation_id>/xlsx', type='http', auth='user')
    def quotation_xlsx(self, quotation_id):
        quote = request.env['taskhub.quotation'].browse(quotation_id)
        quote.check_access('read')
        company = quote.company_id or request.env.company

        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet('Quotation')
        title = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#101F23'})
        label = workbook.add_format({'bold': True, 'font_color': '#3C4F5B'})
        head = workbook.add_format({'bold': True, 'bg_color': '#101F23', 'font_color': '#FFFFFF', 'border': 1})
        cell = workbook.add_format({'border': 1})
        money = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        total = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'top': 2})

        sheet.set_column(0, 0, 44)
        sheet.set_column(1, 1, 30)
        sheet.set_column(2, 3, 9)
        sheet.set_column(4, 6, 14)
        sheet.write(0, 0, '%s · %s' % (company.name, quote.name), title)
        details = [
            ('Client', quote.partner_id.name or quote.client_name or ''),
            ('Contact email', quote.client_email or ''),
            ('RFQ', quote.rfq_id.name or ''),
            ('Date', quote.date and quote.date.strftime('%d/%m/%Y') or ''),
            ('Valid until', quote.valid_until and quote.valid_until.strftime('%d/%m/%Y') or ''),
            ('Currency', quote.currency_id.name),
        ]
        for row, (key, value) in enumerate(details, start=2):
            sheet.write(row, 0, key, label)
            sheet.write(row, 1, value)

        start = len(details) + 3
        for col, header in enumerate(['Item', 'Supplier / source', 'Qty', 'UoM', 'Cost', 'Unit price', 'Amount']):
            sheet.write(start, col, header, head)
        row = start
        for line in quote.line_ids:
            row += 1
            sheet.write(row, 0, line.name, cell)
            sheet.write(row, 1, line.supplier_id.name or line.source_url or '', cell)
            sheet.write_number(row, 2, line.quantity, cell)
            sheet.write(row, 3, line.uom or '', cell)
            sheet.write_number(row, 4, line.cost, money)
            sheet.write_number(row, 5, line.price_unit, money)
            sheet.write_number(row, 6, line.subtotal, money)
        row += 2
        for key, value in [('Untaxed', quote.amount_untaxed), ('VAT %g%%' % quote.vat_rate, quote.amount_tax), ('Total', quote.amount_total)]:
            sheet.write(row, 5, key, label)
            sheet.write_number(row, 6, value, total if key == 'Total' else money)
            row += 1
        workbook.close()

        filename = '%s.xlsx' % quote.name.replace('/', '-')
        return request.make_response(buffer.getvalue(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename)),
        ])
