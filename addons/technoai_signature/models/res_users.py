import re

from odoo import api, fields, models
from odoo.tools import html2plaintext, is_html_empty

EMPLOYEE_FIELDS = {'name', 'job_title', 'mobile_phone', 'work_phone', 'work_email', 'user_id'}
COMPANY_FIELDS = {'name', 'street', 'street2', 'city', 'zip', 'country_id', 'website', 'state_id'}


class ResUsers(models.Model):
    _inherit = 'res.users'

    tai_signature_auto = fields.Boolean(
        'Company signature', default=True,
        help='The signature follows the company design and the employee data; it stops once the user writes their own.')

    def _tai_signature_values(self):
        self.ensure_one()
        # Odoo may give a new user an empty employee of its own: prefer the one filled in
        employees = self.env['hr.employee'].sudo().search([('user_id', '=', self.id)])
        employee = employees.sorted(lambda e: (not e.job_title, not e.mobile_phone))[:1]
        company = self.company_id
        country = company.country_id
        last = ' - '.join(filter(None, [company.city, 'UAE' if country.code == 'AE' else country.name]))
        website = (company.website or '').strip()
        return {
            'name': employee.name or self.name,
            'job': employee.job_title,
            'mobile': employee.mobile_phone or self.partner_id.mobile or employee.work_phone or self.partner_id.phone,
            'email': employee.work_email or self.email,
            'address_lines': [line for line in [
                company.street and '%s,' % company.street.rstrip(','),
                company.street2 and '%s,' % company.street2.rstrip(','),
                last,
            ] if line],
            'website': re.sub(r'^https?://', '', website).rstrip('/'),
            'website_url': website if website.startswith('http') else 'https://%s' % website,
            'logo_url': '%s/technoai_signature/static/img/signature_logo.png' % self.get_base_url(),
        }

    def _tai_render_signature(self):
        self.ensure_one()
        return self.env['ir.qweb']._render('technoai_signature.user_signature', self._tai_signature_values())

    def _tai_refresh_signature(self, force=False):
        """ Write the company signature on internal users who keep it (or on all of them with force). """
        for user in self.filtered(lambda u: not u.share and (force or u.tai_signature_auto)):
            user.with_context(tai_signature=True).sudo().write(
                {'signature': user._tai_render_signature(), 'tai_signature_auto': True})

    def _tai_has_plain_signature(self):
        """ Empty, or Odoo's default "-- name" (in any of its old forms). """
        if is_html_empty(self.signature):
            return True
        text = html2plaintext(self.signature or '').strip()
        core = re.sub(r'[\s\-+*]+', ' ', text).strip()
        return not core or core == self.name or (text.startswith('--') and len(core) <= len(self.name or '') + 20)

    @api.model
    def _tai_apply_company_signature_to_all(self):
        users = self.with_context(active_test=False).search([('share', '=', False), ('id', '!=', self.env.ref('base.public_user').id)])
        plain = users.filtered(lambda u: u.tai_signature_auto and (u._tai_has_plain_signature() or 'Thanks &amp; Regards' in (u.signature or '')
                                                                    or 'Thanks & Regards' in (u.signature or '')))
        (users - plain).filtered('tai_signature_auto').sudo().write({'tai_signature_auto': False})
        plain._tai_refresh_signature()

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users.filtered(lambda u: u._tai_has_plain_signature())._tai_refresh_signature()
        return users

    def write(self, vals):
        if 'signature' in vals and not self.env.context.get('tai_signature') and 'tai_signature_auto' not in vals:
            vals = dict(vals, tai_signature_auto=False)  # the user wrote their own signature
        result = super().write(vals)
        if {'name', 'email', 'mobile', 'company_id'} & set(vals) and not self.env.context.get('tai_signature'):
            self._tai_refresh_signature()
        return result


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.user_id._tai_refresh_signature()
        return employees

    def write(self, vals):
        previous = self.user_id
        result = super().write(vals)
        if EMPLOYEE_FIELDS & set(vals):
            (previous | self.user_id)._tai_refresh_signature()
        return result


class ResCompany(models.Model):
    _inherit = 'res.company'

    def write(self, vals):
        result = super().write(vals)
        if COMPANY_FIELDS & set(vals):
            self.env['res.users'].sudo().search([('company_id', 'in', self.ids), ('share', '=', False)])._tai_refresh_signature()
        return result
