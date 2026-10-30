from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.http import request


class TechnoaiPortalHome(Home):

    @http.route(['/', '/landing'], type='http', auth="none")
    def index(self, s_action=None, db=None, **kw):
        """ Visitors see the landing page; signed-in users also see it via /landing. """
        if request.httprequest.path == '/landing' or kw.get('landing'):
            return request.render('technoai_portal.landing')
        if request.db and not request.session.uid and not kw:
            return request.render('technoai_portal.landing')
        return super().index(s_action=s_action, db=db, **kw)
