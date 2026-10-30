""" Sample data for testing. Every record created here gets an external id in this
module, so uninstalling the module finds and removes exactly these records. """
import logging
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

MODULE = 'technoai_sample_data'

CUSTOMERS = [
    ('Al Safa Trading LLC (Sample)', 'Dubai', 'procurement@alsafa-sample.test', '+971 4 555 0101'),
    ('Gulf Horizon Contracting (Sample)', 'Abu Dhabi', 'info@gulfhorizon-sample.test', '+971 2 555 0102'),
    ('Desert Rose Hotels (Sample)', 'Dubai', 'purchasing@desertrose-sample.test', '+971 4 555 0103'),
    ('Emirates Swift Logistics (Sample)', 'Sharjah', 'ops@swiftlogistics-sample.test', '+971 6 555 0104'),
    ('Falconview Tech Solutions (Sample)', 'Dubai', 'admin@falconview-sample.test', '+971 4 555 0105'),
    ('Marina Facilities Management (Sample)', 'Dubai', 'fm@marinafm-sample.test', '+971 4 555 0106'),
]
VENDORS = [
    ('Prime Office Supplies (Sample)', 'Dubai', 'sales@primeoffice-sample.test'),
    ('TechSource Distribution (Sample)', 'Dubai', 'orders@techsource-sample.test'),
    ('BlueLine IT Hardware (Sample)', 'Sharjah', 'quotes@blueline-sample.test'),
    ('Swift Print Services (Sample)', 'Ajman', 'hello@swiftprint-sample.test'),
]
# name, internal ref, sale price, cost, type
PRODUCTS = [
    ('Business Laptop 14"', 'SMP-LAP14', 4200, 3500, 'consu'),
    ('27" IPS Monitor', 'SMP-MON27', 850, 650, 'consu'),
    ('24-Port Network Switch', 'SMP-SW24', 1600, 1250, 'consu'),
    ('Wireless Access Point', 'SMP-WAP', 720, 540, 'consu'),
    ('Ergonomic Office Chair', 'SMP-CHAIR', 950, 600, 'consu'),
    ('A4 Laser Printer', 'SMP-PRN', 1350, 1050, 'consu'),
    ('IT Support (hour)', 'SMP-SUP', 180, 90, 'service'),
    ('Installation & Setup', 'SMP-INST', 450, 200, 'service'),
]
EMPLOYEES = [
    ('Ahmed Khan', 'Procurement Officer', 'dept_procurement'),
    ('Sara Malik', 'Accountant', 'dept_accounts'),
    ('Bilal Hussain', 'IT Engineer', 'dept_it'),
    ('Fatima Noor', 'HR Executive', 'dept_hr'),
    ('Omar Farooq', 'Operations Manager', 'dept_operations'),
    ('Ayesha Siddiqui', 'Sales Executive', 'dept_admin'),
]


class _Recorder:
    """ Gives each sample record an external id in this module. """

    def __init__(self, env):
        self.env = env
        self.count = {}

    def __call__(self, records, kind):
        for record in records:
            self.count[kind] = self.count.get(kind, 0) + 1
            self.env['ir.model.data'].create({
                'module': MODULE,
                'name': '%s_%s' % (kind, self.count[kind]),
                'model': record._name,
                'res_id': record.id,
                'noupdate': True,
            })
        return records


def _section(env, title, func):
    try:
        with env.cr.savepoint():
            func()
    except Exception:
        _logger.exception('Sample data: could not create %s', title)


def create_sample_data(env):
    keep = _Recorder(env)
    today = fields.Date.context_today(env.user)
    now = fields.Datetime.now()
    user = env.ref('base.user_admin')
    company = env.company
    ae = env.ref('base.ae')
    data = {}

    tag = keep(env['res.partner.category'].create({'name': 'Sample data', 'color': 3}), 'tag')

    def partners():
        cities = {'Dubai': 'Dubai', 'Abu Dhabi': 'Abu Dhabi', 'Sharjah': 'Sharjah', 'Ajman': 'Ajman'}
        data['customers'] = keep(env['res.partner'].create([{
            'name': name, 'is_company': True, 'city': cities[city], 'country_id': ae.id,
            'email': email, 'phone': phone, 'category_id': [(4, tag.id)], 'customer_rank': 1,
        } for name, city, email, phone in CUSTOMERS]), 'customer')
        data['vendors'] = keep(env['res.partner'].create([{
            'name': name, 'is_company': True, 'city': city, 'country_id': ae.id,
            'email': email, 'category_id': [(4, tag.id)], 'supplier_rank': 1,
        } for name, city, email in VENDORS]), 'vendor')

    def products():
        data['products'] = keep(env['product.product'].create([{
            'name': name, 'default_code': code, 'list_price': price, 'standard_price': cost,
            'type': kind, 'sale_ok': True, 'purchase_ok': True,
        } for name, code, price, cost, kind in PRODUCTS]), 'product')

    def sales():
        p = data['products']
        c = data['customers']
        plans = [
            (c[0], [(p[0], 5), (p[1], 5), (p[7], 1)], 'draft', 3),
            (c[1], [(p[2], 2), (p[3], 6), (p[7], 2)], 'sent', 5),
            (c[2], [(p[4], 20)], 'sale', 9),
            (c[3], [(p[5], 3), (p[6], 10)], 'sale', 14),
            (c[4], [(p[0], 12), (p[1], 12)], 'sale', 20),
            (c[5], [(p[6], 24), (p[3], 4)], 'draft', 1),
        ]
        orders = env['sale.order']
        for partner, lines, state, days_ago in plans:
            order = env['sale.order'].create({
                'partner_id': partner.id, 'user_id': user.id,
                'date_order': now - timedelta(days=days_ago),
                'order_line': [(0, 0, {'product_id': prod.id, 'product_uom_qty': qty}) for prod, qty in lines],
            })
            if state == 'sent':
                order.state = 'sent'
            elif state == 'sale':
                order.action_confirm()
            orders |= order
        keep(orders, 'sale_order')
        data['sale_orders'] = orders
        confirmed = orders.filtered(lambda o: o.state == 'sale')
        # deliveries stay open (a done transfer could not be removed again)
        keep(confirmed.picking_ids, 'picking')

    def invoices():
        # invoiced by ordered quantities, since the deliveries stay open
        confirmed = data['sale_orders'].filtered(lambda o: o.state == 'sale')[:2]
        confirmed.order_line.product_id.product_tmpl_id.invoice_policy = 'order'
        moves = env['account.move']
        for order in confirmed:
            moves |= order._create_invoices()
        keep(moves, 'invoice')
        moves[:1].action_post()

    def purchases():
        p = data['products']
        v = data['vendors']
        plans = [
            (v[1], [(p[0], 10), (p[1], 10)], True),
            (v[2], [(p[2], 3), (p[3], 8)], True),
            (v[0], [(p[4], 15)], False),
            (v[3], [(p[5], 2)], False),
        ]
        orders = env['purchase.order']
        for partner, lines, confirm in plans:
            order = env['purchase.order'].create({
                'partner_id': partner.id,
                'order_line': [(0, 0, {'product_id': prod.id, 'product_qty': qty, 'price_unit': prod.standard_price}) for prod, qty in lines],
            })
            if confirm:
                order.button_confirm()
            orders |= order
        keep(orders, 'purchase_order')
        keep(orders.picking_ids, 'receipt')

    def crm():
        stages = env['crm.stage'].search([], order='sequence')
        c = data['customers']
        leads = [
            ('Office network upgrade', c[0], 18500, 0),
            ('Hotel Wi-Fi refresh', c[2], 42000, 1),
            ('Warehouse barcode scanners', c[3], 26000, 2),
            ('Annual IT support contract', c[4], 64800, 1),
            ('New branch fit-out IT', c[5], 35000, 0),
            ('Printer fleet replacement', c[1], 15600, 3),
        ]
        keep(env['crm.lead'].create([{
            'name': name, 'partner_id': partner.id, 'type': 'opportunity', 'user_id': user.id,
            'expected_revenue': revenue, 'probability': 20 + 20 * stage,
            'stage_id': stages[min(stage, len(stages) - 1)].id if stages else False,
            'date_deadline': today + timedelta(days=10 + 7 * i),
        } for i, (name, partner, revenue, stage) in enumerate(leads)]), 'lead')

    def people():
        employees = env['hr.employee']
        for name, job, dept in EMPLOYEES:
            department = env.ref('technoai_taskhub.%s' % dept, raise_if_not_found=False)
            employees |= env['hr.employee'].create({
                'name': name + ' (Sample)', 'job_title': job, 'department_id': department.id if department else False,
                'work_email': name.lower().replace(' ', '.') + '@technoai-sample.test',
            })
        keep(employees, 'employee')
        data['employees'] = employees

    def project():
        prj = keep(env['project.project'].create({'name': 'Office Network Upgrade (Sample)', 'partner_id': data['customers'][0].id}), 'project')
        stages = env['project.task.type'].search([('project_ids', 'in', prj.ids)], order='sequence')
        if not stages:
            stages = keep(env['project.task.type'].create([{'name': n, 'sequence': i, 'project_ids': [(4, prj.id)]}
                                                           for i, n in enumerate(['To Do', 'In Progress', 'Done'])]), 'project_stage')
        tasks = [('Site survey', 2), ('Cable plan and quotation', 2), ('Order switches and access points', 1),
                 ('Install and configure network', 0), ('Handover and training', 0)]
        keep(env['project.task'].create([{
            'name': name, 'project_id': prj.id, 'stage_id': stages[min(s, len(stages) - 1)].id,
            'user_ids': [(4, user.id)], 'date_deadline': now + timedelta(days=3 * i - 3),
        } for i, (name, s) in enumerate(tasks)]), 'project_task')

    def taskhub():
        dept = lambda x: env.ref('technoai_taskhub.%s' % x).id
        c = data['customers']
        tasks = [
            ('Follow up Al Safa quotation', 'high', 'dept_admin', -1, 'todo', c[0]),
            ('Collect supplier prices for switches', 'urgent', 'dept_procurement', -2, 'in_progress', c[1]),
            ('Prepare monthly VAT summary', 'high', 'dept_accounts', 0, 'todo', False),
            ('Onboard new IT engineer', 'medium', 'dept_hr', 1, 'todo', False),
            ('Renew antivirus licences', 'medium', 'dept_it', 3, 'in_progress', False),
            ('Hotel Wi-Fi site visit', 'high', 'dept_operations', 2, 'todo', c[2]),
            ('Send delivery note to Swift Logistics', 'low', 'dept_operations', 5, 'todo', c[3]),
            ('Close March payroll queries', 'medium', 'dept_hr', -5, 'done', False),
        ]
        records = env['taskhub.task']
        for name, priority, d, days, state, partner in tasks:
            task = env['taskhub.task'].create({
                'name': name, 'priority': priority, 'department_id': dept(d), 'user_id': user.id,
                'date_deadline': now + timedelta(days=days, hours=2), 'partner_id': partner.id if partner else False,
                'check_ids': [(0, 0, {'name': step, 'sequence': i}) for i, step in enumerate(['Review details', 'Do the work', 'Confirm with the team'])],
            })
            if state == 'in_progress':
                task.action_start()
            elif state == 'done':
                task.action_mark_done()
            records |= task
        keep(records, 'taskhub_task')

        rfqs = env['taskhub.rfq']
        for partner, subject, lines, state in [
            (c[2], 'RFQ: 40 access points for hotel floors', [('Wireless Access Point', 40), ('Installation & Setup', 1)], 'new'),
            (c[4], 'Quotation request - 12 laptops and monitors', [('Business Laptop 14"', 12), ('27" IPS Monitor', 12)], 'approved'),
            (c[1], 'RFQ for site printers', [('A4 Laser Printer', 4)], 'quoted'),
        ]:
            rfqs |= env['taskhub.rfq'].create({
                'subject': subject, 'partner_id': partner.id, 'client_name': partner.name, 'client_email': partner.email,
                'source': 'email', 'state': state, 'user_id': user.id,
                'email_body': '<p>Dear team,</p><p>Please send your best price for the items below.</p>',
                'line_ids': [(0, 0, {'name': n, 'quantity': q}) for n, q in lines],
            })
        keep(rfqs, 'taskhub_rfq')
        quotation = env['taskhub.quotation'].create({
            'rfq_id': rfqs[1].id, 'partner_id': c[4].id, 'client_name': c[4].name, 'client_email': c[4].email,
            'line_ids': [(0, 0, {'name': 'Business Laptop 14"', 'quantity': 12, 'cost': 3500, 'price_unit': 4150, 'supplier_id': data['vendors'][1].id}),
                         (0, 0, {'name': '27" IPS Monitor', 'quantity': 12, 'cost': 650, 'price_unit': 840, 'supplier_id': data['vendors'][2].id})],
        })
        keep(quotation, 'taskhub_quotation')

    def expenses():
        employee = data['employees'][0]
        product = env['product.product'].search([('can_be_expensed', '=', True)], limit=1)
        keep(env['hr.expense'].create([{
            'name': name, 'employee_id': employee.id, 'total_amount_currency': amount,
            'date': today - timedelta(days=days), **({'product_id': product.id} if product else {}),
        } for name, amount, days in [('Taxi to client site', 85, 2), ('Lunch with supplier', 160, 4)]]), 'expense')

    for title, func in [('partners', partners), ('products', products), ('sales', sales), ('invoices', invoices), ('purchases', purchases),
                        ('CRM', crm), ('employees', people), ('project', project), ('Task Hub', taskhub), ('expenses', expenses)]:
        if title in ('sales', 'purchases', 'project', 'Task Hub', 'CRM') and 'customers' not in data:
            continue
        if title == 'invoices' and 'sale_orders' not in data:
            continue
        _section(env, title, func)
    _logger.info('Sample data created: %s', keep.count)


# deleted children first, so parents are free to go
REMOVE_ORDER = [
    'hr.expense', 'taskhub.quotation', 'taskhub.rfq', 'taskhub.task', 'project.task', 'project.task.type', 'project.project',
    'crm.lead', 'account.move', 'stock.picking', 'purchase.order', 'sale.order', 'hr.employee',
    'product.product', 'res.partner', 'res.partner.category',
]


def remove_sample_data(env):
    """ Cancel and delete the sample records; archive what real work now uses. """
    data = env['ir.model.data'].search([('module', '=', MODULE)])
    by_model = {}
    for row in data:
        by_model.setdefault(row.model, []).append(row.res_id)
    for model in REMOVE_ORDER + [m for m in by_model if m not in REMOVE_ORDER]:
        records = env[model].browse(by_model.get(model, [])).exists() if model in env else None
        if not records:
            continue
        for record in records:
            try:
                with env.cr.savepoint():
                    if model == 'account.move' and record.state == 'posted':
                        record.button_draft()
                    elif model == 'sale.order' and record.state not in ('draft', 'cancel'):
                        record._action_cancel()
                    elif model == 'purchase.order' and record.state != 'cancel':
                        record.button_cancel()
                    elif model == 'stock.picking' and record.state not in ('draft', 'cancel'):
                        if record.state == 'done':
                            raise ValueError('done transfers are kept')
                        record.action_cancel()
                    if model == 'hr.employee':
                        contact = record.work_contact_id
                        record.unlink()
                        contact.unlink()
                    elif model == 'product.product':
                        template = record.product_tmpl_id
                        record.unlink()
                        template.unlink()
                    else:
                        record.unlink()
            except Exception:
                with env.cr.savepoint():
                    if 'active' in record._fields:
                        record.active = False
                _logger.info('Sample data: archived %s %s instead of deleting it', model, record.id)
    # the external ids themselves go with the module
    env['ir.model.data'].search([('module', '=', MODULE)]).unlink()
