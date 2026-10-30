{
    'name': 'Techno AI Sales & Purchase Fields',
    'version': '1.0',
    'category': 'Sales/Sales',
    'summary': 'Remarks, availability, warranty, Tax Excl./Incl. button, margin columns and the sale order letter',
    'description': """
Additions for the way Techno AI works:

* Quotation header: template, remarks, recurring plan label, pricelist,
  delivery date, availability, incoterm and warranty.
* Remarks are copied to the delivery order.
* Order lines: unit cost, margin, margin %, tax excl. and tax incl. columns.
* Purchase orders: payment terms and arrival confirmation in the header.
* A Tax Excl. / Tax Incl. button on sales, purchase and invoice forms. It only
  changes what the Amount column shows, never the calculation.
* The sale order letter (quotation, sales order, pro-forma).
* Full names for the UAE taxes.
""",
    'website': 'https://technoai.ae',
    'depends': ['sale_management', 'sale_stock', 'sale_margin', 'purchase', 'account'],
    'data': [
        'data/sales_ext_data.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
        'views/stock_picking_views.xml',
        'report/sale_order_letter.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'technoai_sales_ext/static/src/scss/tax_display.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
