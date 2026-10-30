{
    'name': 'Techno AI Portal',
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': 'Task Hub landing page at the site root and the Task Hub sign-in look',
    'description': """
Brings the Task Hub's public pages into Techno AI:

* The landing page ("Departmental Task Hub") at the site root; signed-in
  users go straight to the apps.
* The sign-in, password reset and other account pages in the Task Hub's
  dark "Enterprise Employee Sign In" style. Sign-in itself stays Techno AI's.

Uninstall the module to get the previous pages back.
""",
    'website': 'https://technoai.ae',
    'depends': ['web', 'auth_signup'],
    'data': [
        'views/landing.xml',
        'views/login.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'technoai_portal/static/src/scss/login.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
