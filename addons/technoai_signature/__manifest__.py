{
    'name': 'Techno AI Email Signature',
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': "Every employee's email signature in the Techno AI company design",
    'description': """
Gives every internal user the company email signature (Thanks & Regards, the
Techno AI logo, name, job title, mobile, email, office address and website),
filled from the Employees app and the company. It follows changes of the
employee or the company until the user writes their own signature.
""",
    'website': 'https://technoai.ae',
    'depends': ['mail', 'hr'],
    'data': [
        'data/signature_templates.xml',
        'data/signature_data.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
