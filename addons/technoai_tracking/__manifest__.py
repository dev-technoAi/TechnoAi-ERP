{
    'name': 'Order Tracking',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Track every client order item by item, with a public tracking page, QR codes and alerts',
    'description': """
The Techno AI order tracking, inside the ERP. A confirmed Sales Order becomes a
tracked order (client PO number, SO, client, contact, sales person, items).
Each item goes Processing > Ready to Ship from Supplier > In Transit > In
Inventory > Ready for Delivery > Delivered; receipts and deliveries move it on
their own, the rest is set by the team with the ETA and the shipment link.

Clients follow their order on /track (or by the QR code on the quotation and
the delivery note) and can subscribe to email updates. The team is alerted on
status changes, on completed orders and on late items.
""",
    'website': 'https://technoai.ae',
    'depends': ['mail', 'sale_stock', 'purchase_stock', 'sale_purchase', 'technoai_sales_ext', 'technoai_taskhub'],
    'data': [
        'security/tracking_security.xml',
        'security/ir.model.access.csv',
        'data/tracking_data.xml',
        'views/tracking_order_views.xml',
        'views/tracking_line_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/tracking_menus.xml',
        'views/tracking_public_templates.xml',
        'report/tracking_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'technoai_tracking/static/src/dashboard/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
