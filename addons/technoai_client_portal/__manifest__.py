{
    'name': 'Techno AI Client Portal',
    'version': '1.0',
    'category': 'Website',
    'summary': "Clients sign in at /clientportal and see their own quotations, orders, tracking, deliveries and invoices, live",
    'description': """
The Techno AI client portal at /clientportal, with its own sign-in page.
A client (a portal user invited from the contact) sees only their company's
documents, straight from the ERP: quotations to accept, orders with the
item-by-item tracking, delivery notes, invoices and a statement, each in
its own currency. Clients can send a request for quotation (it lands in
Task Hub) and message the team on an order.
""",
    'website': 'https://technoai.ae',
    'depends': ['portal', 'sale_stock', 'account', 'technoai_tracking', 'technoai_taskhub'],
    'data': [
        'views/client_portal_templates.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
