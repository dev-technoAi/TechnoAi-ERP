from datetime import timedelta

from odoo import api, fields, models

TICKET_LIFETIME = timedelta(minutes=2)


class TechnoaiSsoTicket(models.Model):
    """ One row per Task Hub ticket, so each ticket opens at most one session. """
    _name = 'technoai.sso.ticket'
    _description = 'Task Hub sign-in ticket'

    nonce = fields.Char(required=True, index=True)
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    used = fields.Boolean()

    _sql_constraints = [
        ('nonce_unique', 'UNIQUE(nonce)', 'A sign-in ticket can only be used once.'),
    ]

    @api.model
    def _consume(self, nonce, user):
        """ Mark the ticket as used; return True if it was valid for this user. """
        ticket = self.sudo().search([
            ('nonce', '=', nonce),
            ('user_id', '=', user.id),
            ('used', '=', False),
            ('create_date', '>=', fields.Datetime.now() - TICKET_LIFETIME),
        ], limit=1)
        if not ticket:
            return False
        ticket.used = True
        return True

    @api.model
    def _gc_tickets(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()
