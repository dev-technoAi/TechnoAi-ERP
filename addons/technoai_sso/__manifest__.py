{
    'name': 'Techno AI Task Hub Sign-In',
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': 'Sign in to Techno AI through the Task Hub login page',
    'description': """
Users sign in on the Task Hub, which hands Techno AI a short-lived signed
ticket. Techno AI checks the signature, matches the user by email and opens
their session. Only users that already exist in Techno AI can sign in.

Configuration (odoo.conf):
    technoai_sso_secret = shared secret, same as TECHNOAI_SSO_SECRET in the Task Hub
    technoai_sso_login_url = Task Hub login page, e.g. http://localhost:3001/login
    technoai_sso_taskhub_url = Task Hub workspace, e.g. http://localhost:3001/dashboard
    technoai_sso_home_url = Task Hub landing page, e.g. http://localhost:3001/

The regular login form stays available at /web/login?local=1.
""",
    'website': 'https://technoai.ae',
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'views/technoai_sso_menus.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
