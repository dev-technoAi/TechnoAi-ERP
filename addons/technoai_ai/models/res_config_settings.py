from odoo import _, fields, models

from .ai_providers import DEFAULT_MODELS, PROVIDERS, AiProviderError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    technoai_ai_provider = fields.Selection(
        [('anthropic', 'Claude (Anthropic)'), ('openai', 'OpenAI (ChatGPT)'), ('gemini', 'Google Gemini')],
        'AI provider', default='anthropic', config_parameter='technoai_ai.provider')
    technoai_ai_anthropic_key = fields.Char('Claude API key', config_parameter='technoai_ai.anthropic_key')
    technoai_ai_anthropic_model = fields.Char('Claude model', config_parameter='technoai_ai.anthropic_model', default=DEFAULT_MODELS['anthropic'])
    technoai_ai_openai_key = fields.Char('OpenAI API key', config_parameter='technoai_ai.openai_key')
    technoai_ai_openai_model = fields.Char('OpenAI model', config_parameter='technoai_ai.openai_model', default=DEFAULT_MODELS['openai'])
    technoai_ai_gemini_key = fields.Char('Gemini API key', config_parameter='technoai_ai.gemini_key')
    technoai_ai_gemini_model = fields.Char('Gemini model', config_parameter='technoai_ai.gemini_model', default=DEFAULT_MODELS['gemini'])

    def action_technoai_ai_test(self):
        """ Save, then send the chosen provider a one-line question. """
        self.execute()
        settings = self.env['technoai.ai.chat']._ai_settings()
        try:
            provider = PROVIDERS[settings['provider']](settings['api_key'], settings['model'])
            history = []
            provider.add_user_text(history, 'Reply with just: OK')
            reply = provider.complete(history, 'You are a connection test.', [])
        except AiProviderError as error:
            message, kind = str(error), 'danger'
        else:
            message, kind = _('Connected to %(model)s. It replied: %(reply)s', model=settings['model'], reply=(reply.text or '')[:60]), 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': kind, 'title': _('Techno AI assistant'), 'message': message, 'sticky': kind == 'danger'},
        }
