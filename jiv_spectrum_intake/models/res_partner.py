from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ── Client Profile fields (mirrors crm.lead x_studio_* fields) ──────────
    # Excludes phone/email/name which already exist on res.partner natively.

    # Section 1 — Client Info
    x_studio_date_of_birth = fields.Date(string='Date of Birth')
    x_studio_emergency_contact_name = fields.Char(string='Emergency Contact Name')
    x_studio_emergency_contact_phone = fields.Char(string='Emergency Contact Phone')
    x_studio_emergency_contact_relationship = fields.Char(string='Emergency Contact Relationship')

    # Section 2 — Payer / Funding
    x_studio_payer_type = fields.Selection(
        selection=lambda self: self._get_lead_selection('x_studio_payer_type'),
        string='Payer Type',
    )
    x_studio_referral_date = fields.Date(string='Referral Date')
    x_studio_claim_reference_ = fields.Char(string='Claim / Reference #')
    x_studio_case_manager_name = fields.Char(string='Case Manager Name')
    x_studio_case_manager_phone = fields.Char(string='Case Manager Phone')
    x_studio_case_manager_email = fields.Char(string='Case Manager Email')
    x_studio_bill_to = fields.Many2one('res.partner', string='Insurance / Funding Source')

    # Section 3 — Services
    x_studio_service_types = fields.Many2many(
        'x_lead_service_types',
        'partner_service_types_rel',
        'partner_id', 'service_type_id',
        string='Service Types',
    )
    x_studio_service_description = fields.Char(string='Service Description')
    x_studio_authorized_hoursweek = fields.Float(string='Authorized Hours/Week')
    x_studio_service_rate = fields.Monetary(string='Service Rate', currency_field='currency_id')
    x_studio_monthly_authorized_budget = fields.Monetary(string='Monthly Authorized Budget', currency_field='currency_id')
    x_studio_budgetauthorization_expiry_date = fields.Date(string='Budget/Authorization Expiry Date')

    # Section 4 — Schedule
    x_studio_desired_start_date = fields.Date(string='Desired Start Date')
    x_studio_estimated_hoursweek = fields.Float(string='Estimated Hours/Week')
    x_studio_preferred_days = fields.Many2many(
        'x_lead_preferred_days',
        'partner_preferred_days_rel',
        'partner_id', 'day_id',
        string='Preferred Days',
    )
    x_studio_preferred_time_of_day = fields.Selection(
        selection=lambda self: self._get_lead_selection('x_studio_preferred_time_of_day'),
        string='Preferred Time of Day',
    )

    # Section 5 — Care Considerations
    x_studio_mobility_needs = fields.Char(string='Mobility Needs')
    x_studio_allergies_medical_conditions = fields.Char(string='Allergies / Medical Conditions')
    x_studio_medications = fields.Char(string='Medications')
    x_studio_caregiver_gender_preference = fields.Selection(
        selection=lambda self: self._get_lead_selection('x_studio_caregiver_gender_preference'),
        string='Caregiver Gender Preference',
    )
    x_studio_language_preference = fields.Char(string='Language Preference')
    x_studio_pets_in_home = fields.Char(string='Pets in Home')
    x_studio_access_instructions = fields.Char(string='Access Instructions')

    # Section 6 — Care Team
    x_studio_physician_name = fields.Char(string='Physician Name')
    x_studio_physician_phone = fields.Char(string='Physician Phone')
    x_studio_ot_name = fields.Char(string='OT Name')
    x_studio_ot_phone = fields.Char(string='OT Phone')

    # Section 7 — Consent
    x_studio_consent_contact_by_phoneemail = fields.Boolean(
        string='Consent to Contact by Phone/Email')

    # ── Currency (needed for Monetary fields) ────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
    )

    def _get_lead_selection(self, field_name):
        """Pull selection values from the crm.lead field definition."""
        field = self.env['ir.model.fields'].sudo().search([
            ('model', '=', 'crm.lead'),
            ('name', '=', field_name),
        ], limit=1)
        if field:
            return [(s.value, s.name) for s in field.selection_ids.sorted('sequence')]
        return []
