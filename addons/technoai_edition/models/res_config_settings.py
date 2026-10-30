from odoo import api, fields, models

# Screens of the paid credit services (lead mining, enrichment, company autocomplete, SMS).
# Their view extensions and menus are archived while hidden (inherited views cannot carry
# groups, and a menu's groups widen its access); the SMS actions get the group instead.
PAID_VIEWS = (
    'crm_iap_enrich.crm_lead_view_form',
    'crm_iap_mine.crm_case_kanban_view_leads',
    'crm_iap_mine.crm_lead_view_tree_lead',
    'crm_iap_mine.crm_lead_view_tree_opportunity',
    'crm_iap_mine.view_crm_lead_kanban',
    'partner_autocomplete.view_company_form_inherit_partner_autocomplete',
    'partner_autocomplete.view_partner_simple_form_inherit_partner_autocomplete',
    'partner_autocomplete.view_res_partner_form_inherit_partner_autocomplete',
)
PAID_ACTIONS = (
    'sms.res_partner_act_window_sms_composer_multi',
    'sms.res_partner_act_window_sms_composer_single',
)
PAID_MENUS = (
    'crm_iap_mine.crm_menu_lead_generation',
    'crm_iap_mine.crm_iap_lead_mining_request_menu_action',
    'iap.iap_root_menu',
    'sms.sms_sms_menu',
    'sms.sms_template_menu',
    'snailmail.menu_snailmail_letters',
)
PAID_WIDGETS = ('upgrade_boolean', 'iap_buy_more_credits')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    group_technoai_paid_features = fields.Boolean(
        'Show paid features', implied_group='technoai_edition.group_paid_features',
        help='Show Enterprise-only options, paid apps and the paid credit services (SMS, lead generation, enrichment, autocomplete).')

    def set_values(self):
        super().set_values()
        self._technoai_apply_paid_visibility()

    @api.model
    def _technoai_show_paid(self):
        group = self.env.ref('technoai_edition.group_paid_features', raise_if_not_found=False)
        return bool(group) and group in self.env.ref('base.group_user').sudo().implied_ids

    @api.model
    def _technoai_apply_paid_visibility(self):
        """ Show or hide the paid apps, menus, actions and screens, following the setting. """
        show = self._technoai_show_paid()
        group = self.env.ref('technoai_edition.group_paid_features')
        apps = self.env.ref('base.open_module_tree').sudo()
        apps.domain = False if show else "[('to_buy', '=', False)]"
        for xmlid in PAID_ACTIONS:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                action.sudo().groups_id = [(3, group.id)] if show else [(4, group.id)]
        for xmlid in PAID_VIEWS + PAID_MENUS:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.sudo().active = show
        self.env.registry.clear_cache('templates')

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        return super()._get_view_cache_key(view_id, view_type, **options) + (
            self.env.user.has_group('technoai_edition.group_paid_features'),)

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """ Unless paid features are shown, drop the settings that need an Enterprise
        subscription or paid credits, and the blocks they leave empty. """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form' and not self.env.user.has_group('technoai_edition.group_paid_features'):
            blocks = set()
            paid = '|'.join("//field[@widget='%s']|//widget[@name='%s']" % (widget, widget) for widget in PAID_WIDGETS)
            for field in arch.xpath(paid):
                setting = next(field.iterancestors('setting'), None)
                node = setting if setting is not None else field
                if node.getparent() is None:
                    continue  # already dropped with another paid field of the same setting
                blocks.update(node.iterancestors('block'))
                node.getparent().remove(node)
            for block in blocks:
                if not block.xpath('.//setting') and block.getparent() is not None:
                    block.getparent().remove(block)
        return arch, view
