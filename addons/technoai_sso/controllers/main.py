import base64
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlencode

import psycopg2

from odoo import SUPERUSER_ID, api, http
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools import config

from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.session import Session
from odoo.addons.web.controllers.utils import _get_login_redirect_url, ensure_db

_logger = logging.getLogger(__name__)

# tickets are signed for 60 seconds by the Task Hub; allow a little clock skew
MAX_TICKET_AGE = 120


def _sso_settings():
    return {
        'secret': (config.get('technoai_sso_secret') or '').strip(),
        'login_url': (config.get('technoai_sso_login_url') or '').strip(),
        'taskhub_url': (config.get('technoai_sso_taskhub_url') or '').strip(),
        'home_url': (config.get('technoai_sso_home_url') or '').strip(),
    }


def _sso_enabled():
    settings = _sso_settings()
    return bool(settings['secret'] and settings['login_url'])


def _b64decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _verify_ticket(ticket, secret):
    """ Return the payload of a valid Task Hub ticket, or None. """
    try:
        data, signature = ticket.split('.')
        expected = hmac.new(secret.encode(), data.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            return None
        payload = json.loads(_b64decode(data))
    except (ValueError, TypeError):
        return None
    now = time.time()
    exp = payload.get('exp', 0) / 1000
    if not (now < exp <= now + MAX_TICKET_AGE):
        return None
    if not isinstance(payload.get('email'), str) or len(payload.get('nonce') or '') < 16:
        return None
    return payload


def _safe_redirect(path):
    # only same-site paths, never //host or absolute URLs
    if isinstance(path, str) and path.startswith('/') and not path.startswith('//') and '\\' not in path:
        return path
    return '/technoai'


def _back_to_login(**params):
    url = _sso_settings()['login_url']
    if params:
        url += ('&' if '?' in url else '?') + urlencode(params)
    return request.redirect(url, local=False)


class TechnoaiSso(http.Controller):

    @http.route('/technoai/sso', type='http', auth='none', methods=['POST'], csrf=False)
    def technoai_sso(self, ticket=None, **kw):
        if not _sso_enabled():
            return request.not_found()
        ensure_db()
        payload = _verify_ticket(ticket or '', _sso_settings()['secret'])
        if not payload:
            _logger.warning("Task Hub sign-in rejected: invalid or expired ticket")
            return _back_to_login(technoai_error='expired')

        email = payload['email'].strip().lower()
        with request.env.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = env['res.users'].search([
                ('share', '=', False),
                '|', ('login', '=ilike', email), ('email', '=ilike', email),
            ])
            # an exact login match wins; otherwise the email must point to exactly one user
            user = users.filtered(lambda u: u.login.lower() == email)[:1] or (users if len(users) == 1 else users.browse())
            if not user:
                _logger.info("Task Hub sign-in refused for %s: no matching Techno AI user", email)
                return _back_to_login(technoai_error='no_account')
            login = user.login
            try:
                with cr.savepoint():
                    env['technoai.sso.ticket'].create({'nonce': payload['nonce'], 'user_id': user.id})
            except psycopg2.IntegrityError:
                _logger.warning("Task Hub sign-in rejected for %s: ticket already used", email)
                return _back_to_login(technoai_error='expired')
            env['technoai.sso.ticket']._gc_tickets()

        try:
            auth_info = request.session.authenticate(request.db, {
                'type': 'technoai_sso',
                'login': login,
                'nonce': payload['nonce'],
            })
        except AccessDenied:
            return _back_to_login(technoai_error='denied')
        return request.redirect(_get_login_redirect_url(auth_info['uid'], _safe_redirect(payload.get('redirect'))))

    @http.route('/technoai/taskhub', type='http', auth='user')
    def technoai_taskhub(self, **kw):
        url = _sso_settings()['taskhub_url']
        if not url:
            return request.not_found()
        return request.redirect(url, local=False)


class TechnoaiSsoHome(Home):

    @http.route()
    def index(self, s_action=None, db=None, **kw):
        # visitors who are not signed in see the Task Hub landing page
        home_url = _sso_settings()['home_url']
        if _sso_enabled() and home_url and not request.session.uid:
            return request.redirect(home_url, local=False)
        return super().index(s_action=s_action, db=db, **kw)

    @http.route()
    def web_login(self, redirect=None, **kw):
        # the Task Hub login page replaces this form; /web/login?local=1 keeps it reachable
        if (_sso_enabled() and request.httprequest.method == 'GET' and not kw.get('local')
                and 'error' not in kw and not request.session.uid):
            params = {'redirect': redirect} if redirect else {}
            return _back_to_login(**params)
        return super().web_login(redirect=redirect, **kw)


class TechnoaiSsoSession(Session):

    @http.route()
    def logout(self, redirect='/technoai'):
        if not _sso_enabled():
            return super().logout(redirect=redirect)
        request.session.logout(keep_db=True)
        # also end the Task Hub session, otherwise its login page signs the user straight back in
        return _back_to_login(signout=1)
