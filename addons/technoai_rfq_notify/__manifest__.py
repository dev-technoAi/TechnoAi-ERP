{
    'name': 'RFQ Mail Notification',
    'version': '1.0',
    'category': 'Productivity',
    'summary': "Alerts each employee on the browser, phone and WhatsApp when an RFQ reaches their own mailbox",
    'description': """
Every employee adds their own technoai.ae mailbox (Zoho). The app checks it every
minute, read-only, and when an RFQ arrives, or a later email from a client who
sent one, it alerts that employee in the browser and on the phone (web push), in
the ERP inbox and on WhatsApp. The email opens in the ERP with its attachments,
and replies go out from the employee's own mailbox with their own signature.

RFQs also become Email RFQs in Task Hub, assigned to the mailbox's owner.
""",
    'website': 'https://technoai.ae',
    'depends': ['mail', 'hr', 'technoai_taskhub'],
    'data': [
        'security/rfq_notify_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'wizard/rfq_notify_compose_views.xml',
        'views/rfq_notify_mailbox_views.xml',
        'views/rfq_notify_message_views.xml',
        'views/res_config_settings_views.xml',
        'views/rfq_notify_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'technoai_rfq_notify/static/src/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
