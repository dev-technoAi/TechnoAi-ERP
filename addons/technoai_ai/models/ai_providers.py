""" Thin HTTP clients for the AI providers the assistant can use.

Each provider keeps the conversation in its own wire format, so what the model
returned (thinking blocks, signatures, fallback blocks) is sent back unchanged
on the next request. A chat therefore stays on the provider it started with.
"""
import json
import logging

import requests

_logger = logging.getLogger(__name__)

TIMEOUT = 180

DEFAULT_MODELS = {
    'anthropic': 'claude-opus-5-5',
    'openai': 'gpt-5',
    'gemini': 'gemini-2.5-flash',
}

# Claude models that accept server-side refusal fallbacks ("default" routing)
ANTHROPIC_FALLBACK_MODELS = ('claude-fable-5-1', 'claude-opus-5-5', 'claude-opus-5', 'claude-sonnet-5-5')


class AiProviderError(Exception):
    pass


class ToolCall:
    def __init__(self, call_id, name, args):
        self.id = call_id
        self.name = name
        self.args = args if isinstance(args, dict) else {}

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'args': self.args}

    @classmethod
    def from_dict(cls, data):
        return cls(data['id'], data['name'], data['args'])


class Reply:
    def __init__(self, text='', calls=(), refused=False, truncated=False):
        self.text = text
        self.calls = list(calls)
        self.refused = refused
        self.truncated = truncated


class Provider:
    name = None

    def __init__(self, api_key, model):
        if not api_key:
            raise AiProviderError('No API key is set for this AI provider. An administrator can add it in Settings > Techno AI assistant.')
        self.api_key = api_key
        self.model = model or DEFAULT_MODELS[self.name]

    def _post(self, url, headers, payload):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise AiProviderError('Could not reach the AI provider: %s' % error) from error
        if response.status_code >= 400:
            try:
                detail = response.json().get('error') or response.json()
                detail = detail.get('message') if isinstance(detail, dict) else detail
            except ValueError:
                detail = response.text[:300]
            _logger.warning('AI provider %s returned %s: %s', self.name, response.status_code, detail)
            raise AiProviderError('The AI provider returned an error (%s): %s' % (response.status_code, detail))
        return response.json()

    # history is a list of provider-native messages, changed in place
    def add_user_text(self, history, text):
        raise NotImplementedError

    def complete(self, history, system, tools):
        """ Ask the model for its next turn, append it to history and return a Reply. """
        raise NotImplementedError

    def add_tool_results(self, history, results):
        """ results: list of (ToolCall, result dict, is_error) answering the last turn's calls """
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = 'anthropic'

    def add_user_text(self, history, text):
        history.append({'role': 'user', 'content': text})

    def complete(self, history, system, tools):
        headers = {
            'content-type': 'application/json',
            'x-api-key': self.api_key,
            'anthropic-version': '2026-10-21',
        }
        payload = {
            'model': self.model,
            'max_tokens': 16000,
            'system': system,
            'tools': [{'name': t['name'], 'description': t['description'], 'input_schema': t['parameters']} for t in tools],
            'messages': history,
            'cache_control': {'type': 'ephemeral'},
        }
        if not tools:
            del payload['tools']
        if self.model in ANTHROPIC_FALLBACK_MODELS:
            headers['anthropic-beta'] = 'server-side-fallback-2026-07-01'
            payload['fallbacks'] = 'default'
            payload['output_config'] = {'effort': 'medium'}
        data = self._post('https://api.anthropic.com/v1/messages', headers, payload)
        if data.get('stop_reason') == 'refusal':
            # nothing usable came back; drop the unanswered question so the chat can go on
            if history and history[-1]['role'] == 'user' and isinstance(history[-1]['content'], str):
                history.pop()
            return Reply(refused=True)
        content = data.get('content') or []
        history.append({'role': 'assistant', 'content': content})
        return Reply(
            text='\n\n'.join(block['text'] for block in content if block.get('type') == 'text' and block.get('text')),
            calls=[ToolCall(block['id'], block['name'], block.get('input')) for block in content if block.get('type') == 'tool_use'],
            truncated=data.get('stop_reason') == 'max_tokens',
        )

    def add_tool_results(self, history, results):
        history.append({'role': 'user', 'content': [{
            'type': 'tool_result',
            'tool_use_id': call.id,
            'content': json.dumps(result, default=str),
            **({'is_error': True} if is_error else {}),
        } for call, result, is_error in results]})


class OpenAIProvider(Provider):
    name = 'openai'

    def add_user_text(self, history, text):
        history.append({'role': 'user', 'content': text})

    def complete(self, history, system, tools):
        payload = {
            'model': self.model,
            'messages': [{'role': 'system', 'content': system}] + history,
        }
        if tools:
            payload['tools'] = [{'type': 'function', 'function': tool} for tool in tools]
        data = self._post('https://api.openai.com/v1/chat/completions',
                          {'Authorization': 'Bearer %s' % self.api_key, 'Content-Type': 'application/json'}, payload)
        choice = (data.get('choices') or [{}])[0]
        message = {k: v for k, v in (choice.get('message') or {}).items() if v is not None}
        message['role'] = 'assistant'
        history.append(message)
        calls = []
        for call in message.get('tool_calls') or []:
            try:
                args = json.loads(call['function'].get('arguments') or '{}')
            except ValueError:
                args = {}
            calls.append(ToolCall(call['id'], call['function']['name'], args))
        return Reply(text=message.get('content') or '', calls=calls,
                     refused=bool(message.get('refusal')), truncated=choice.get('finish_reason') == 'length')

    def add_tool_results(self, history, results):
        for call, result, _is_error in results:
            history.append({'role': 'tool', 'tool_call_id': call.id, 'content': json.dumps(result, default=str)})


class GeminiProvider(Provider):
    name = 'gemini'

    def add_user_text(self, history, text):
        history.append({'role': 'user', 'parts': [{'text': text}]})

    def complete(self, history, system, tools):
        payload = {
            'systemInstruction': {'parts': [{'text': system}]},
            'contents': history,
        }
        if tools:
            payload['tools'] = [{'functionDeclarations': tools}]
        data = self._post('https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent' % self.model,
                          {'x-goog-api-key': self.api_key, 'Content-Type': 'application/json'}, payload)
        candidate = (data.get('candidates') or [{}])[0]
        content = candidate.get('content') or {}
        parts = content.get('parts') or []
        if not parts:
            if history and history[-1]['role'] == 'user' and any('text' in part for part in history[-1]['parts']):
                history.pop()
            return Reply(refused=True)
        history.append({'role': 'model', 'parts': parts})
        calls = [ToolCall(part['functionCall'].get('id') or part['functionCall']['name'], part['functionCall']['name'], part['functionCall'].get('args'))
                 for part in parts if 'functionCall' in part]
        return Reply(text='\n\n'.join(part['text'] for part in parts if part.get('text') and not part.get('thought')),
                     calls=calls, truncated=candidate.get('finishReason') == 'MAX_TOKENS')

    def add_tool_results(self, history, results):
        history.append({'role': 'user', 'parts': [{'functionResponse': {
            'name': call.name,
            **({'id': call.id} if call.id != call.name else {}),
            'response': {'error': result} if is_error else {'result': result},
        }} for call, result, is_error in results]})


PROVIDERS = {cls.name: cls for cls in (AnthropicProvider, OpenAIProvider, GeminiProvider)}
