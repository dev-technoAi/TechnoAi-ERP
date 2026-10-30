from odoo import api, models

# the UAE chart's short tax names, by (use, name)
FULL_NAMES = {
    ('sale', '5% DB'): 'VAT 5% (Dubai)',
    ('sale', '5% AD'): 'VAT 5% (Abu Dhabi)',
    ('sale', '5% S'): 'VAT 5% (Sharjah)',
    ('sale', '5% A'): 'VAT 5% (Ajman)',
    ('sale', '5% UAQ'): 'VAT 5% (Umm Al Quwain)',
    ('sale', '5% RAK'): 'VAT 5% (Ras Al Khaimah)',
    ('sale', '5% F'): 'VAT 5% (Fujairah)',
    ('sale', '0% Exempt'): 'VAT Exempt 0%',
    ('sale', '0%'): 'VAT Zero-rated 0%',
    ('sale', '0% EX'): 'VAT 0% (Export)',
    ('sale', '5% R C D'): 'Reverse Charge 5% (Dubai)',
    ('sale', '5% R C AD'): 'Reverse Charge 5% (Abu Dhabi)',
    ('sale', '5% R C S'): 'Reverse Charge 5% (Sharjah)',
    ('sale', '5% R C A'): 'Reverse Charge 5% (Ajman)',
    ('sale', '5% R C UAQ'): 'Reverse Charge 5% (Umm Al Quwain)',
    ('sale', '5% R C RAK'): 'Reverse Charge 5% (Ras Al Khaimah)',
    ('sale', '5% R C F'): 'Reverse Charge 5% (Fujairah)',
    ('sale', '5% T R'): 'Tourist Refund 5%',
    ('purchase', '5%'): 'VAT 5%',
    ('purchase', '0% Exempt'): 'VAT Exempt 0%',
    ('purchase', '0%'): 'VAT Zero-rated 0%',
    ('purchase', '5% EX'): 'VAT 5% (Import)',
    ('purchase', '5% R C'): 'Reverse Charge 5%',
}


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.model
    def _technoai_set_full_names(self):
        """ Give the UAE taxes readable names; anything renamed by hand is left alone. """
        taxes = self.with_context(active_test=False, lang='en_US').search([('country_id.code', '=', 'AE')])
        for tax in taxes:
            new_name = FULL_NAMES.get((tax.type_tax_use, tax.name))
            if new_name:
                tax.name = new_name
