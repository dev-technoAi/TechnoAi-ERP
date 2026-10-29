import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import ai_tools
from .ai_providers import DEFAULT_MODELS, PROVIDERS, AiProviderError, ToolCall

_logger = logging.getLogger(__name__)

MAX_ROUNDS = 8

SYSTEM_PROMPT = """You are Techno AI, the assistant built into the Techno AI ERP of the company. \
People use you from any screen to look things up, get totals and charts, and get routine work done.

How to work:
- Answer from the company's real data by calling the tools; never invent records, numbers or names. \
If you are not sure of a model or field name, use find_models and get_fields first.
- When the user asks for particular records (latest order, an invoice, a customer), call search_records with show=true \
so they get cards with an Open button. For totals, rankings and "chart of ..." questions use aggregate, with a chart when it helps.
- To change anything (create, update, press a button, send or log a message) call the matching tool. \
The user then sees a confirmation card and approves or cancels it, so do not ask "shall I?" in text first; just call the tool \
with complete, correct values (look up ids of related records before). After a cancel, ask what they want instead.
- Reply in the user's language and script (English, Urdu, or Roman Urdu), short and to the point. Give amounts with their currency.
- The system is called Techno AI. Do not mention any other product name, and do not show technical model or field names unless asked.
- You can only see and do what this user is allowed to; if a tool says access is denied, say so plainly."""


class TechnoaiAiChat(models.Model):
    _name = 'technoai.ai.chat'
    _description = 'AI assistant conversation'
    _order = 'write_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New chat'))
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, ondelete='cascade', index=True)
    provider = fields.Char(required=True, readonly=True)
    model_name = fields.Char(readonly=True)
    history = fields.Json(default=list, help='Conversation in the provider\'s own message format.')
    items = fields.Json(default=list, help='What the chat panel shows.')
    pending = fields.Json(help='Tool calls waiting for the user\'s confirmation.')

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------

    @api.model
    def _ai_settings(self):
        params = self.env['ir.config_parameter'].sudo()
        provider = params.get_param('technoai_ai.provider') or 'anthropic'
        return {
            'provider': provider,
            'api_key': params.get_param('technoai_ai.%s_key' % provider),
            'model': params.get_param('technoai_ai.%s_model' % provider) or DEFAULT_MODELS[provider],
        }

    def _provider(self):
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        return PROVIDERS[self.provider](params.get_param('technoai_ai.%s_key' % self.provider), self.model_name)

    # ------------------------------------------------------------------
    # API used by the chat panel
    # ------------------------------------------------------------------

    def _panel_data(self):
        self.ensure_one()
        return {'id': self.id, 'name': self.name, 'items': self.items or [], 'pending': bool(self.pending)}

    @api.model
    def ai_list_chats(self):
        chats = self.search([('user_id', '=', self.env.uid)], limit=30)
        return [{'id': chat.id, 'name': chat.name, 'date': fields.Datetime.to_string(chat.write_date)} for chat in chats]

    @api.model
    def ai_status(self):
        settings = self._ai_settings()
        return {'configured': bool(settings['api_key']), 'is_admin': self.env.user.has_group('base.group_system')}

    def ai_load(self):
        return self._panel_data()

    @api.model
    def ai_send(self, chat_id, text, page=None):
        """ Add the user's message, let the model work, and return what the panel shows. """
        text = (text or '').strip()
        if not text:
            raise UserError(_('Type a message first.'))
        chat = self.browse(chat_id).exists() if chat_id else self.browse()
        if not chat:
            settings = self._ai_settings()
            chat = self.create({'provider': settings['provider'], 'model_name': settings['model'], 'name': text[:60]})
        if chat.pending:
            # a new message instead of answering the card counts as "no"
            chat._resolve_pending(approve=False, note='The user did not confirm and wrote a new message instead.', carry_on=False)
        items = list(chat.items or [])
        items.append({'type': 'user', 'text': text})
        history = list(chat.history or [])
        prompt = text
        if page and page.get('title'):
            prompt = '%s\n\n[Screen the user is on: %s%s]' % (
                text, page['title'], ' (%s, record %s)' % (page.get('model'), page['res_id']) if page.get('res_id') else
                (' (%s)' % page['model'] if page.get('model') else ''))
        try:
            provider = chat._provider()
            provider.add_user_text(history, prompt)
            chat._run(provider, history, items)
        except AiProviderError as error:
            items.append({'type': 'error', 'text': str(error)})
            chat.write({'items': items})
        return chat._panel_data()

    def ai_confirm(self, approve, change=False):
        self.ensure_one()
        if not self.pending:
            return self._panel_data()
        note = None
        if change:
            note = 'The user wants to change this before it is done. Ask what to change.'
        try:
            self._resolve_pending(approve=approve, note=note)
        except AiProviderError as error:
            self.write({'items': (self.items or []) + [{'type': 'error', 'text': str(error)}]})
        return self._panel_data()

    def ai_rename(self, name):
        self.write({'name': (name or '').strip()[:80] or _('New chat')})
        return True

    # ------------------------------------------------------------------
    # the agent loop
    # ------------------------------------------------------------------

    def _system_prompt(self):
        return '%s\n\n%s' % (SYSTEM_PROMPT, ai_tools.context_line(self.env))

    def _run(self, provider, history, items):
        """ Call the model until it answers in text or asks for a confirmation. Saves the chat. """
        self.ensure_one()
        system = self._system_prompt()
        for _round in range(MAX_ROUNDS):
            reply = provider.complete(history, system, ai_tools.TOOLS)
            if reply.refused:
                items.append({'type': 'error', 'text': _('The AI declined to answer this request. Try asking it differently.')})
                break
            if reply.text:
                items.append({'type': 'text', 'text': reply.text})
            if not reply.calls:
                if reply.truncated:
                    items.append({'type': 'error', 'text': _('The answer was cut off because it was too long.')})
                break
            results, waiting = self._call_tools(reply.calls, items)
            if waiting:
                self.write({'history': history, 'items': items, 'pending': {
                    'done': [[call.to_dict(), result, is_error] for call, result, is_error in results],
                    'waiting': [call.to_dict() for call in waiting],
                }})
                return
            provider.add_tool_results(history, results)
        else:
            items.append({'type': 'error', 'text': _('Stopped after too many steps. Ask a narrower question.')})
        self.write({'history': history, 'items': items, 'pending': False})

    def _call_tools(self, calls, items):
        """ Run read tools; turn write tools into confirmation cards. """
        results, waiting = [], []
        for call in calls:
            if call.name in ai_tools.WRITE_TOOLS:
                try:
                    card = ai_tools.preview(self.env, call.name, call.args)
                except (ai_tools.ToolError, UserError, ValueError) as error:
                    results.append((call, {'error': str(error)}, True))
                    continue
                items.append(dict(card, type='confirm', call_id=call.id, state='pending'))
                waiting.append(call)
                continue
            tool = ai_tools.READ_TOOLS.get(call.name)
            try:
                if not tool:
                    raise ai_tools.ToolError('Unknown tool %s.' % call.name)
                with self.env.cr.savepoint():
                    result, new_items = tool(self.env, **call.args)
                items.append({'type': 'step', 'text': self._step_label(call)})
                items.extend(new_items)
                results.append((call, ai_tools.trim(result), False))
            except (ai_tools.ToolError, UserError, ValueError, TypeError, KeyError) as error:
                results.append((call, {'error': str(error)}, True))
            except Exception as error:  # access errors and constraint errors are answers too
                _logger.info('AI tool %s failed: %s', call.name, error)
                results.append((call, {'error': str(error)}, True))
        return results, waiting

    def _step_label(self, call):
        args = call.args
        model = args.get('model')
        label = model and model in self.env and self.env[model]._description or model or ''
        return {
            'find_models': _('Looked up where "%s" is kept', args.get('query', '')),
            'get_fields': _('Checked the fields of %s', label),
            'search_records': _('Searched %s', label),
            'aggregate': _('Totalled %s', label),
            'open_view': _('Prepared a link to %s', label),
        }.get(call.name, call.name)

    def _resolve_pending(self, approve, note=None, carry_on=True):
        """ Run (or skip) the calls waiting for confirmation, then let the model carry on. """
        self.ensure_one()
        pending = self.pending or {}
        items = list(self.items or [])
        results = [(ToolCall.from_dict(call), result, is_error) for call, result, is_error in pending.get('done', [])]
        for data in pending.get('waiting', []):
            call = ToolCall.from_dict(data)
            card = next((item for item in items if item.get('type') == 'confirm' and item.get('call_id') == call.id), None)
            if not approve:
                results.append((call, {'cancelled': True, 'note': note or 'The user cancelled this.'}, False))
                if card:
                    card['state'] = 'changed' if note and 'change' in note else 'cancelled'
                continue
            try:
                with self.env.cr.savepoint():
                    result, new_items = ai_tools.run(self.env, call.name, call.args)
                results.append((call, result, False))
                items.extend(new_items)
                if card:
                    card['state'] = 'done'
            except Exception as error:
                results.append((call, {'error': str(error)}, True))
                items.append({'type': 'error', 'text': str(error)})
                if card:
                    card['state'] = 'failed'
        history = list(self.history or [])
        provider = self._provider()
        provider.add_tool_results(history, results)
        # saved first: every tool call must keep its answer even if the next request fails
        self.write({'pending': False, 'history': history, 'items': items})
        if carry_on:
            self._run(provider, list(history), list(items))
