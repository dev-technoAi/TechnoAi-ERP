{
    'name': 'Sales Order from Excel',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Create an ordinary Sales quotation from a costing sheet (Excel)',
    'description': """
Sales > Quotations > Upload Excel: choose the customer and the sheet, check the
items, and an ordinary quotation is created, exactly as with the New button.

From the sheet: the description, the quantity, the selling price (the margin
column) and the lead time, written under each item. Cost, supplier, links,
delivery and contact columns stay private and are not put on the order. VAT is
the company's 5% unless 0% is chosen. Nothing else in Sales changes.
""",
    'website': 'https://technoai.ae',
    'depends': ['sale_management', 'technoai_taskhub'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/sale_excel_import_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
