{
    'name': 'Techno AI Sample Data',
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': 'Test data for trying Techno AI; uninstall the module to remove it',
    'description': """
Fills Techno AI with a small, made-up company dataset for testing:
customers and vendors (tagged "Sample data"), products, quotations and sales
orders with invoices, RFQs and purchase orders, CRM opportunities, employees,
a project, Task Hub tasks, email RFQs and a draft quotation, and expenses.

Every record it creates is listed under this module. Uninstalling it deletes
them again (records that real work now depends on are archived instead).
""",
    'website': 'https://technoai.ae',
    'depends': ['sale_management', 'purchase', 'stock', 'account', 'crm', 'project', 'hr', 'hr_expense', 'technoai_taskhub'],
    'post_init_hook': 'create_sample_data',
    'uninstall_hook': 'remove_sample_data',
    'installable': True,
    'license': 'LGPL-3',
}
