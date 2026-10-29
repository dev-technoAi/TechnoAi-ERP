{
    'name': 'Techno AI Edition',
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': 'Hide paid Enterprise options and turn on the free full accounting features',
    'description': """
Keeps Techno AI to what is free and installed here:

* Settings: options that need a paid Enterprise subscription are hidden,
  together with the sections that only held such options.
* Apps: paid apps (the ones with an "Upgrade" button) are not listed.
* Invoicing: accounting administrators get the full accounting features
  (Journal Entries, Chart of Accounts, journals, reports, ...).

Uninstall the module to get the previous behaviour back.
""",
    'website': 'https://technoai.ae',
    'depends': ['base_setup', 'account'],
    'data': [
        'data/edition_data.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
