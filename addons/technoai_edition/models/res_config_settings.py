from odoo import api, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """ Drop the settings that need a paid Enterprise subscription, and the blocks they leave empty. """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            blocks = set()
            for field in arch.xpath("//field[@widget='upgrade_boolean']"):
                setting = next(field.iterancestors('setting'), None)
                node = setting if setting is not None else field
                if node.getparent() is None:
                    continue  # already dropped with another Enterprise field of the same setting
                blocks.update(node.iterancestors('block'))
                node.getparent().remove(node)
            for block in blocks:
                if not block.xpath('.//setting') and block.getparent() is not None:
                    block.getparent().remove(block)
        return arch, view
