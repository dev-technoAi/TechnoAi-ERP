{
    'name': 'Techno AI Backend Theme',
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': 'Left sidebar navigation and Techno AI colours for the backend',
    'description': """
Moves the main navigation (apps, app sections and their submenus) from the
top bar into a dark left sidebar and applies the Techno AI colours.

Only the presentation changes: every menu, submenu, hotkey, systray item and
view keeps its behaviour. Phones keep Techno AI's own burger menu. Uninstall the
module to get the previous layout back.
""",
    'website': 'https://technoai.ae',
    'depends': ['web'],
    'data': [
        'data/home_action.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'technoai_backend_theme/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'technoai_backend_theme/static/src/scss/sidebar.scss',
            'technoai_backend_theme/static/src/webclient/navbar_patch.js',
            'technoai_backend_theme/static/src/webclient/ui_size_patch.js',
            'technoai_backend_theme/static/src/webclient/navbar.xml',
            'technoai_backend_theme/static/src/home/home_action.js',
            'technoai_backend_theme/static/src/home/home_header.xml',
            'technoai_backend_theme/static/src/home/home_header.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
