{
    'name': 'Techno AI Supplier Portal',
    'version': '1.0',
    'category': 'Website',
    'summary': 'Suppliers sign in at /supplierportal to quote RFQs, accept purchase orders, update shipments and see payments',
    'description': """
The Techno AI supplier portal at /supplierportal, with its own sign-in page.
A supplier (a portal user invited from the supplier's contact) sees only its
own company's RFQs, purchase orders, vendor bills and payments.

* Prices sent on an RFQ go onto the purchase lines and into Task Hub sourcing
  (Known suppliers ranks them); the buyer is alerted.
* Accepting a PO and updating its shipment (ready to ship, shipped with the
  carrier and tracking number) moves the client's Order Tracking on its own.
* Invoices and packing lists are uploaded on the PO; messages reach the buyer.
""",
    'website': 'https://technoai.ae',
    'depends': ['technoai_client_portal', 'purchase_stock', 'technoai_tracking', 'technoai_taskhub'],
    'data': [
        'views/purchase_order_views.xml',
        'views/supplier_portal_templates.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
