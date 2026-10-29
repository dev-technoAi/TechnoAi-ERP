from odoo import models
from odoo.exceptions import AccessDenied


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _check_credentials(self, credential, env):
        if credential.get('type') != 'technoai_sso':
            return super()._check_credentials(credential, env)
        # the ticket row only exists if the controller verified the Task Hub signature
        if not self.env['technoai.sso.ticket']._consume(credential.get('nonce'), self.env.user):
            raise AccessDenied()
        return {
            'uid': self.env.user.id,
            'auth_method': 'technoai_sso',
            'mfa': 'default',
        }
