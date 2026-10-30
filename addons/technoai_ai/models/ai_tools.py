""" The tools the assistant can call. Everything runs as the signed-in user, so
access rights and record rules decide what the assistant can see and change.

Read tools run straight away. Write tools (WRITE_TOOLS) only describe what
they would do; the chat shows a confirmation card and runs them on "Yes".
"""
import json

from odoo import fields
from odoo.tools import html2plaintext, plaintext2html

MAX_RESULT_CHARS = 20000

TOOLS = [
    {
        'name': 'find_models',
        'description': 'Find the data models (tables) to work with, by keyword in English, e.g. "purchase order", "invoice", "task", "employee". '
                       'Returns technical model names such as purchase.order. Use this first when you are not sure of the model name.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Keyword, e.g. "sales order"'},
        }, 'required': ['query']},
    },
    {
        'name': 'get_fields',
        'description': 'List the fields of a model (name, label, type, related model, selection values). '
                       'Call it before filtering or creating so you use real field names.',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string', 'description': 'Technical model name, e.g. sale.order'},
            'query': {'type': 'string', 'description': 'Optional keyword to only list matching fields'},
        }, 'required': ['model']},
    },
    {
        'name': 'search_records',
        'description': 'Search records and read their fields. Set show=true to show the records to the user as cards with an Open button '
                       '(use it when the user asked for specific records, e.g. "latest PO of X").',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string'},
            'domain': {'type': 'string', 'description': 'Search filter as a JSON list, e.g. [["partner_id.name", "ilike", "Azure"], ["state", "=", "purchase"]]. Use [] for all.'},
            'fields': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Field names to read; keep it short'},
            'order': {'type': 'string', 'description': 'e.g. "date_order desc"'},
            'limit': {'type': 'integer', 'description': 'At most 50, default 10'},
            'show': {'type': 'boolean', 'description': 'Show the records to the user as cards'},
        }, 'required': ['model', 'domain']},
    },
    {
        'name': 'aggregate',
        'description': 'Group records and total a numeric field (or count them), optionally drawn as a chart for the user. '
                       'groupby can be a field or a date with granularity, e.g. "partner_id", "state", "date_order:month".',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string'},
            'domain': {'type': 'string', 'description': 'JSON list filter, [] for all'},
            'groupby': {'type': 'string'},
            'measure': {'type': 'string', 'description': 'Numeric field to total, e.g. amount_total. Leave empty to count records.'},
            'chart': {'type': 'string', 'enum': ['pie', 'bar', 'line', 'none'], 'description': 'Chart to show the user'},
            'title': {'type': 'string', 'description': 'Chart title'},
            'limit': {'type': 'integer', 'description': 'Largest groups to keep, default 10'},
        }, 'required': ['model', 'domain', 'groupby']},
    },
    {
        'name': 'open_view',
        'description': 'Give the user a button that opens a list, kanban, graph, pivot or form view of records in the app.',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string'},
            'domain': {'type': 'string', 'description': 'JSON list filter, [] for all'},
            'view_type': {'type': 'string', 'enum': ['list', 'kanban', 'form', 'graph', 'pivot', 'calendar']},
            'record_id': {'type': 'integer', 'description': 'For a form view of one record'},
            'label': {'type': 'string', 'description': 'Button text'},
        }, 'required': ['model', 'view_type', 'label']},
    },
    {
        'name': 'create_record',
        'description': 'Create a record. The user sees a confirmation card first; it is only created when they approve.',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string'},
            'values': {'type': 'string', 'description': 'JSON object of field values; many2one fields take the record id, e.g. {"name": "Call Azure", "user_id": 7}'},
            'summary': {'type': 'string', 'description': 'Short title for the confirmation card'},
        }, 'required': ['model', 'values', 'summary']},
    },
    {
        'name': 'update_records',
        'description': 'Change field values of existing records. The user confirms first.',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string'},
            'ids': {'type': 'array', 'items': {'type': 'integer'}},
            'values': {'type': 'string', 'description': 'JSON object of the new field values'},
            'summary': {'type': 'string'},
        }, 'required': ['model', 'ids', 'values', 'summary']},
    },
    {
        'name': 'run_action',
        'description': 'Press a button on records, i.e. call a public method whose name starts with action_ or button_ '
                       '(e.g. sale.order action_confirm, account.move action_post). The user confirms first.',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string'},
            'ids': {'type': 'array', 'items': {'type': 'integer'}},
            'method': {'type': 'string'},
            'summary': {'type': 'string'},
        }, 'required': ['model', 'ids', 'method', 'summary']},
    },
    {
        'name': 'post_message',
        'description': 'Post a message in the chatter of a record. With send_email=true it is emailed to the followers (e.g. the customer); '
                       'otherwise it is an internal note. The user confirms first.',
        'parameters': {'type': 'object', 'properties': {
            'model': {'type': 'string'},
            'record_id': {'type': 'integer'},
            'body': {'type': 'string', 'description': 'Plain text message'},
            'send_email': {'type': 'boolean'},
            'summary': {'type': 'string'},
        }, 'required': ['model', 'record_id', 'body', 'summary']},
    },
]

WRITE_TOOLS = ('create_record', 'update_records', 'run_action', 'post_message')


class ToolError(Exception):
    pass


def _model(env, name, operation='read'):
    if not name or name not in env:
        raise ToolError('Unknown model %r. Use find_models to get the right name.' % name)
    model = env[name]
    if model._abstract or model._transient:
        raise ToolError('%s cannot be used here.' % name)
    if not model.has_access(operation):
        raise ToolError('You are not allowed to %s %s records.' % (operation, model._description))
    return model


def _json(value, default, label):
    if value in (None, ''):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except ValueError:
        raise ToolError('%s is not valid JSON.' % label)


def _domain(value):
    domain = _json(value, [], 'domain')
    if not isinstance(domain, list):
        raise ToolError('domain must be a JSON list.')
    return [tuple(term) if isinstance(term, list) else term for term in domain]


def _plain(model, record_values, field_names):
    """ Make read() values compact and readable for the model and the cards. """
    fields_info = model._fields
    out = {}
    for name in field_names:
        value = record_values.get(name)
        field = fields_info.get(name)
        if field is None:
            continue
        if field.type == 'many2one':
            value = value[1] if value else None
        elif field.type in ('one2many', 'many2many'):
            value = '%s records' % len(value or [])
        elif field.type == 'html':
            value = html2plaintext(value or '')[:500]
        elif field.type == 'selection' and value:
            value = dict(field._description_selection(model.env)).get(value, value)
        elif value is False and field.type != 'boolean':
            value = None
        out[name] = value
    return out


def _record_card(model, record_id, display_name, values):
    labels = {name: model._fields[name].string for name in values if name in model._fields}
    return {
        'id': record_id,
        'name': display_name,
        'fields': [[labels.get(name, name), '' if value is None else str(value)]
                   for name, value in values.items() if name not in ('id', 'display_name', 'name') and value not in (None, '')][:6],
    }


# ----------------------------------------------------------------------
# read tools: return (result for the model, items for the chat)
# ----------------------------------------------------------------------

def find_models(env, query):
    Model = env['ir.model']
    words = (query or '').split()
    domain = [('transient', '=', False)]
    for word in words:
        domain += ['|', ('model', 'ilike', word), ('name', 'ilike', word)]
    found = []
    for model in Model.sudo().search(domain, limit=60):
        if model.model in env and not env[model.model]._abstract and env[model.model].has_access('read'):
            found.append({'model': model.model, 'name': model.name})
        if len(found) >= 15:
            break
    return {'models': found}, []


def get_fields(env, model, query=None):
    records = _model(env, model)
    attributes = ['string', 'type', 'relation', 'selection', 'required', 'readonly', 'store']
    described = records.fields_get(attributes=attributes)
    query = (query or '').lower()
    result = []
    for name, info in sorted(described.items()):
        if query and query not in name.lower() and query not in (info.get('string') or '').lower():
            continue
        entry = {'name': name, 'label': info.get('string'), 'type': info.get('type')}
        if info.get('relation'):
            entry['model'] = info['relation']
        if info.get('selection'):
            entry['values'] = [key for key, _label in info['selection']][:20]
        for flag in ('required', 'readonly'):
            if info.get(flag):
                entry[flag] = True
        if not info.get('store', True):
            entry['stored'] = False
        result.append(entry)
    return {'model': model, 'fields': result[:150], 'more': max(0, len(result) - 150)}, []


def search_records(env, model, domain, fields=None, order=None, limit=10, show=False):
    records = _model(env, model)
    domain = _domain(domain)
    limit = max(1, min(int(limit or 10), 50))
    field_names = [name for name in (fields or []) if name in records._fields] or [
        name for name in ('name', 'partner_id', 'date', 'date_order', 'state', 'amount_total', 'user_id') if name in records._fields
    ][:6]
    try:
        rows = records.search_read(domain, field_names, order=order or None, limit=limit)
        total = records.search_count(domain)
    except ValueError as error:
        raise ToolError(str(error))
    names = dict(records.browse([row['id'] for row in rows]).mapped(lambda r: (r.id, r.display_name)))
    plain_rows = [{**_plain(records, row, field_names), 'id': row['id'], 'display_name': names.get(row['id'])} for row in rows]
    items = []
    if show and plain_rows:
        items.append({
            'type': 'records',
            'model': model,
            'model_name': records._description,
            'records': [_record_card(records, row['id'], row['display_name'], row) for row in plain_rows[:10]],
        })
    return {'total': total, 'records': plain_rows}, items


def _group_by_path(records, domain, path, measure):
    """ Group on a related path such as partner_id.country_id, which SQL grouping does not support. """
    totals = {}
    for record in records.search(domain, limit=20000):
        key = record.mapped(path)
        key = key[:1] if hasattr(key, '_name') else (key[0] if key else False)
        totals[key] = totals.get(key, 0) + (record[measure] if measure else 1)
    return list(totals.items())


def aggregate(env, model, domain, groupby, measure=None, chart='none', title=None, limit=10):
    records = _model(env, model)
    domain = _domain(domain)
    group_field = groupby.split(':')[0]
    if group_field.split('.')[0] not in records._fields:
        raise ToolError('%s has no field %s.' % (model, group_field))
    if measure and measure not in records._fields:
        raise ToolError('%s has no field %s.' % (model, measure))
    aggregates = ['%s:sum' % measure] if measure else ['__count']
    try:
        if '.' in group_field and records._fields[group_field.split('.')[0]].type != 'properties':
            groups = _group_by_path(records, domain, group_field, measure)
        else:
            groups = records._read_group(domain, [groupby], aggregates)
    except (ValueError, KeyError) as error:
        raise ToolError(str(error))
    data = []
    for group_value, total in groups:
        if hasattr(group_value, 'display_name'):
            label = group_value.display_name or 'None'
        elif group_value in (False, None):
            label = 'None'
        else:
            label = str(group_value.date() if hasattr(group_value, 'date') and groupby.endswith((':month', ':year', ':quarter', ':week')) else group_value)
            selection = records._fields.get(group_field)
            if selection and selection.type == 'selection':
                label = dict(selection._description_selection(env)).get(group_value, label)
        data.append([label, round(total or 0, 2)])
    data.sort(key=lambda pair: pair[1], reverse=chart != 'line')
    limit = max(1, min(int(limit or 10), 30))
    if len(data) > limit and chart != 'line':
        data = data[:limit - 1] + [['Others', round(sum(value for _l, value in data[limit - 1:]), 2)]]
    if chart == 'line':
        data.sort(key=lambda pair: pair[0])
    items = []
    if chart and chart != 'none' and data:
        items.append({
            'type': 'chart',
            'chart': chart,
            'title': title or '',
            'labels': [label for label, _v in data],
            'values': [value for _l, value in data],
            'measure': records._fields[measure].string if measure else 'Count',
            'action': {'model': model, 'domain': domain, 'groupby': groupby, 'measure': measure},
        })
    return {'measure': measure or 'count', 'groups': data}, items


def open_view(env, model, view_type, label, domain=None, record_id=None):
    records = _model(env, model)
    if view_type == 'form' and record_id and not records.browse(record_id).exists():
        raise ToolError('Record %s of %s does not exist.' % (record_id, model))
    item = {'type': 'link', 'label': label, 'model': model, 'view_type': view_type,
            'domain': _domain(domain), 'record_id': record_id or False, 'title': records._description}
    return {'shown': True}, [item]


READ_TOOLS = {f.__name__: f for f in (find_models, get_fields, search_records, aggregate, open_view)}


# ----------------------------------------------------------------------
# write tools: preview() checks and describes, run() does it after "Yes"
# ----------------------------------------------------------------------

def _display_values(records, values):
    rows = []
    for name, value in values.items():
        field = records._fields.get(name)
        if field is None:
            raise ToolError('%s has no field %s.' % (records._name, name))
        shown = value
        if field.type == 'many2one' and value:
            target = records.env[field.comodel_name].browse(int(value)).exists()
            if not target:
                raise ToolError('%s %s does not exist.' % (field.comodel_name, value))
            shown = target.display_name
        elif field.type in ('many2many', 'one2many'):
            shown = '%s lines' % len(value) if isinstance(value, list) else str(value)
        elif field.type == 'selection' and value:
            shown = dict(field._description_selection(records.env)).get(value, value)
        elif field.type == 'boolean':
            shown = 'Yes' if value else 'No'
        elif field.type == 'html':
            shown = html2plaintext(value or '')[:200]
        rows.append([field.string, '' if shown in (None, False) else str(shown)])
    return rows


def preview(env, name, args):
    """ Validate a write call and return the confirmation card, without changing anything. """
    model = args.get('model')
    summary = args.get('summary') or name.replace('_', ' ').capitalize()
    if name == 'create_record':
        records = _model(env, model, 'create')
        values = _json(args.get('values'), {}, 'values')
        return {'title': summary, 'model_name': records._description, 'action': 'Create', 'fields': _display_values(records, values)}
    if name == 'update_records':
        records = _model(env, model, 'write').browse(args.get('ids') or []).exists()
        if not records:
            raise ToolError('No such %s records.' % model)
        values = _json(args.get('values'), {}, 'values')
        return {'title': summary, 'model_name': records._description, 'action': 'Update',
                'fields': [['Records', ', '.join(records.mapped('display_name'))[:200]]] + _display_values(records, values)}
    if name == 'run_action':
        method = args.get('method') or ''
        records = _model(env, model, 'write').browse(args.get('ids') or []).exists()
        if not method.startswith(('action_', 'button_')) or not callable(getattr(records, method, None)):
            raise ToolError('%s is not a button of %s.' % (method, model))
        if not records:
            raise ToolError('No such %s records.' % model)
        return {'title': summary, 'model_name': records._description, 'action': 'Run',
                'fields': [['Records', ', '.join(records.mapped('display_name'))[:200]], ['Button', method]]}
    if name == 'post_message':
        record = _model(env, model).browse(args.get('record_id')).exists()
        if not record or not hasattr(record, 'message_post'):
            raise ToolError('Messages cannot be posted on this record.')
        return {'title': summary, 'model_name': record._description, 'action': 'Send email' if args.get('send_email') else 'Log note',
                'fields': [['Record', record.display_name], ['Message', (args.get('body') or '')[:400]]]}
    raise ToolError('Unknown tool %s.' % name)


def run(env, name, args):
    """ Do an approved write call. Returns (result for the model, items for the chat). """
    model = args.get('model')
    if name == 'create_record':
        records = _model(env, model, 'create')
        record = records.create(_json(args.get('values'), {}, 'values'))
        return {'created': True, 'id': record.id, 'name': record.display_name}, [
            {'type': 'records', 'model': model, 'model_name': records._description, 'badge': 'Created',
             'records': [{'id': record.id, 'name': record.display_name, 'fields': []}]}]
    if name == 'update_records':
        records = _model(env, model, 'write').browse(args.get('ids') or []).exists()
        records.write(_json(args.get('values'), {}, 'values'))
        return {'updated': records.ids}, [
            {'type': 'records', 'model': model, 'model_name': records._description, 'badge': 'Updated',
             'records': [{'id': r.id, 'name': r.display_name, 'fields': []} for r in records[:10]]}]
    if name == 'run_action':
        method = args['method']
        if not method.startswith(('action_', 'button_')):
            raise ToolError('%s is not a button.' % method)
        records = _model(env, model, 'write').browse(args.get('ids') or []).exists()
        result = getattr(records, method)()
        opened = isinstance(result, dict) and result.get('type') == 'ir.actions.act_window'
        return {'done': True, 'opens_a_window': opened}, [
            {'type': 'records', 'model': model, 'model_name': records._description, 'badge': 'Done',
             'records': [{'id': r.id, 'name': r.display_name, 'fields': []} for r in records[:10]]}]
    if name == 'post_message':
        record = _model(env, model).browse(args['record_id']).exists()
        subtype = 'mail.mt_comment' if args.get('send_email') else 'mail.mt_note'
        message = record.message_post(body=plaintext2html(args.get('body') or ''), message_type='comment', subtype_xmlid=subtype)
        return {'posted': True, 'message_id': message.id}, [
            {'type': 'records', 'model': model, 'model_name': record._description, 'badge': 'Sent' if args.get('send_email') else 'Logged',
             'records': [{'id': record.id, 'name': record.display_name, 'fields': []}]}]
    raise ToolError('Unknown tool %s.' % name)


def trim(result):
    """ JSON-safe copy of a tool result (dates become strings), cut down when it is too long. """
    text = json.dumps(result, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return json.loads(text)
    return {'truncated': True, 'partial': text[:MAX_RESULT_CHARS]}


def context_line(env):
    user = env.user
    company = env.company
    return 'User: %s. Company: %s (currency %s). Today: %s. Time zone: %s.' % (
        user.name, company.name, company.currency_id.name, fields.Date.context_today(user), user.tz or 'UTC')
