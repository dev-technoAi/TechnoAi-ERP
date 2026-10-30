{
    'name': 'Techno AI Edition',
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': 'Hide paid options (with a switch to show them) and turn on the free full accounting features',
    'description': """
Keeps Techno AI to what is free and installed here:

* Settings: options that need a paid Enterprise subscription or paid credits
  are hidden, together with the sections that only held such options.
* Apps: paid apps (the ones with an "Upgrade" button) are not listed.
* Paid credit services (SMS, lead generation, lead enrichment, company
  autocomplete, post letters) lose their buttons and menus.
* All of the above comes back with Settings > Show paid features.
* Sales: the empty quotations page shows no vendor video or marketing link.
* Invoicing: accounting administrators get the full accounting features
  (Journal Entries, Chart of Accounts, journals, reports, ...).

Uninstall the module to get the previous behaviour back.
""",
    'website': 'https://technoai.ae',
    'depends': ['base_setup', 'account', 'sale'],
    'data': [
        'security/technoai_edition_security.xml',
        'data/edition_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'technoai_edition/static/src/sale/sale_action_helper.xml',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}
