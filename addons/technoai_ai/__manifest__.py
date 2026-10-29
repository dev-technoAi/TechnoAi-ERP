{
    'name': 'Techno AI Assistant',
    'version': '1.0',
    'category': 'Productivity',
    'summary': 'AI assistant in the top bar: answers from your records, makes charts and does work after you confirm',
    'description': """
An AI button in the top bar opens a chat panel on every page.

* Answers questions from the records the user is allowed to see
  (search, totals, latest documents) with buttons to open them.
* Draws pie, bar and line charts from grouped data.
* Creates and updates records, runs buttons and posts messages, always after
  a confirmation card the user approves.
* Works with Claude (Anthropic), OpenAI or Google Gemini; the provider, model
  and API key are chosen in Settings.

Also adds a Tools menu in the top bar for administrators.
""",
    'website': 'https://technoai.ae',
    'depends': ['base_setup', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/technoai_ai_security.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'technoai_ai/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
