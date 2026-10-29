{
    'name': 'Task Hub',
    'version': '1.0',
    'category': 'Productivity',
    'summary': 'Departmental tasks, due alerts, templates and team for Techno AI',
    'description': """
Task Hub inside Techno AI: departmental tasks with checklists, due alerts with
snooze and alert sounds, reusable templates and team members, linked to the
other Techno AI apps (customers, sales, purchases, invoices, leads).

The module keeps its data in its own tables: uninstalling it removes Task Hub
without touching the rest of Techno AI, and Configuration > Reset Task Hub
data clears test data while keeping templates, departments and the team.
""",
    'website': 'https://technoai.ae',
    'depends': ['mail', 'hr', 'sale_management', 'purchase'],
    'data': [
        'security/taskhub_security.xml',
        'security/ir.model.access.csv',
        'data/hr_department_data.xml',
        'data/taskhub_template_data.xml',
        'data/ir_cron_data.xml',
        'data/taskhub_rfq_data.xml',
        'report/taskhub_quotation_report.xml',
        'data/taskhub_mail_template_data.xml',
        'wizard/taskhub_team_member_views.xml',
        'wizard/taskhub_reset_views.xml',
        'wizard/taskhub_dispatch_views.xml',
        'views/res_config_settings_views.xml',
        'views/taskhub_task_views.xml',
        'views/taskhub_template_views.xml',
        'views/taskhub_rfq_views.xml',
        'views/taskhub_quotation_views.xml',
        'views/taskhub_supplier_views.xml',
        'views/hr_employee_views.xml',
        'views/res_users_views.xml',
        'views/taskhub_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'technoai_taskhub/static/src/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
