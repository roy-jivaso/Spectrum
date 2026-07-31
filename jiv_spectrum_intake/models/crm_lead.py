import uuid
from odoo import models, fields, api

# Fields to sync between crm.lead and res.partner.
# Excludes phone/email which map differently on each model.
# Format: (lead_field, partner_field)
SYNC_FIELDS = [
    ('x_studio_date_of_birth',                  'x_studio_date_of_birth'),
    ('x_studio_emergency_contact_name',          'x_studio_emergency_contact_name'),
    ('x_studio_emergency_contact_phone',         'x_studio_emergency_contact_phone'),
    ('x_studio_emergency_contact_relationship',  'x_studio_emergency_contact_relationship'),
    ('x_studio_payer_type',                      'x_studio_payer_type'),
    ('x_studio_bill_to',                         'x_studio_bill_to'),
    ('x_studio_claim_reference_',                'x_studio_claim_reference_'),
    ('x_studio_referral_date',                   'x_studio_referral_date'),
    ('x_studio_case_manager_name',               'x_studio_case_manager_name'),
    ('x_studio_case_manager_phone',              'x_studio_case_manager_phone'),
    ('x_studio_case_manager_email',              'x_studio_case_manager_email'),
    ('x_studio_service_description',             'x_studio_service_description'),
    ('x_studio_authorized_hoursweek',            'x_studio_authorized_hoursweek'),
    ('x_studio_service_rate',                    'x_studio_service_rate'),
    ('x_studio_monthly_authorized_budget',       'x_studio_monthly_authorized_budget'),
    ('x_studio_budgetauthorization_expiry_date', 'x_studio_budgetauthorization_expiry_date'),
    ('x_studio_desired_start_date',              'x_studio_desired_start_date'),
    ('x_studio_estimated_hoursweek',             'x_studio_estimated_hoursweek'),
    ('x_studio_preferred_time_of_day',           'x_studio_preferred_time_of_day'),
    ('x_studio_mobility_needs',                  'x_studio_mobility_needs'),
    ('x_studio_allergies_medical_conditions',    'x_studio_allergies_medical_conditions'),
    ('x_studio_medications',                     'x_studio_medications'),
    ('x_studio_caregiver_gender_preference',     'x_studio_caregiver_gender_preference'),
    ('x_studio_language_preference',             'x_studio_language_preference'),
    ('x_studio_pets_in_home',                    'x_studio_pets_in_home'),
    ('x_studio_access_instructions',             'x_studio_access_instructions'),
    ('x_studio_physician_name',                  'x_studio_physician_name'),
    ('x_studio_physician_phone',                 'x_studio_physician_phone'),
    ('x_studio_ot_name',                         'x_studio_ot_name'),
    ('x_studio_ot_phone',                        'x_studio_ot_phone'),
    ('x_studio_consent_contact_by_phoneemail',   'x_studio_consent_contact_by_phoneemail'),
]

# Many2many fields need special handling
M2M_SYNC = [
    ('x_studio_service_types',  'x_studio_service_types'),
    ('x_studio_preferred_days', 'x_studio_preferred_days'),
]


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # Token fields for intake form
    x_intake_token = fields.Char(
        string='Intake Token', copy=False, readonly=True, index=True)
    x_intake_submitted = fields.Boolean(
        string='Intake Form Submitted', default=False, copy=False, readonly=True)
    x_intake_submitted_date = fields.Datetime(
        string='Intake Submitted On', copy=False, readonly=True)

    def _get_or_create_intake_token(self):
        self.ensure_one()
        if not self.x_intake_token:
            self.x_intake_token = uuid.uuid4().hex
        return self.x_intake_token

    def action_send_intake_form(self):
        self.ensure_one()
        self._get_or_create_intake_token()
        template = self.env.ref(
            'jiv_spectrum_intake.email_template_intake_form',
            raise_if_not_found=False)
        default_email = self.partner_id.email or self.email_from or ''
        default_name = (
            self.partner_id.name or self.partner_name or self.contact_name or '')
        ctx = {
            'default_model': 'crm.lead',
            'default_res_ids': self.ids,
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'default_partner_ids': self.partner_id.ids if self.partner_id else [],
            'default_email_to': default_email,
            'default_email_from': self.env.user.email_formatted,
            'force_email': True,
            'intake_url': self._get_intake_url(),
            'recipient_name': default_name,
            'recipient_email': default_email,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Intake Form',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': ctx,
        }

    def _get_intake_url(self):
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base}/intake/{self.x_intake_token}"

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------
    def _sync_to_partner(self, write_vals):
        """Push intake values to the linked partner."""
        self.ensure_one()
        if not self.partner_id:
            return
        partner_vals = {}
        for lead_f, partner_f in SYNC_FIELDS:
            if lead_f in write_vals:
                partner_vals[partner_f] = write_vals[lead_f]
        for lead_f, partner_f in M2M_SYNC:
            if lead_f in write_vals:
                partner_vals[partner_f] = write_vals[lead_f]
        if partner_vals:
            self.partner_id.sudo().write(partner_vals)

    def _sync_from_partner(self):
        """Pull profile values from partner into this lead (fills blanks only)."""
        self.ensure_one()
        if not self.partner_id:
            return
        p = self.partner_id
        vals = {}
        for lead_f, partner_f in SYNC_FIELDS:
            lead_val = getattr(self, lead_f, False)
            partner_val = getattr(p, partner_f, False)
            if not lead_val and partner_val:
                vals[lead_f] = partner_val.id if hasattr(partner_val, 'id') \
                    else partner_val
        for lead_f, partner_f in M2M_SYNC:
            lead_val = getattr(self, lead_f, False)
            partner_val = getattr(p, partner_f, False)
            if not lead_val and partner_val:
                vals[lead_f] = [(6, 0, partner_val.ids)]
        if vals:
            self.sudo().write(vals)

    @api.onchange('partner_id')
    def _onchange_partner_id_sync_profile(self):
        """When partner is set on opportunity, pull profile from partner."""
        if self.partner_id and self.type == 'opportunity':
            self._sync_from_partner()

    # ------------------------------------------------------------------
    # Submit intake form
    # ------------------------------------------------------------------
    @api.model
    def submit_intake_form(self, token, values):
        lead = self.sudo().search([('x_intake_token', '=', token)], limit=1)
        if not lead:
            return {'status': 'error', 'message': 'Invalid or expired link.'}

        write_vals = {}

        # Section 1 — Client Information
        if values.get('date_of_birth'):
            write_vals['x_studio_date_of_birth'] = values['date_of_birth']
        if values.get('phone'):
            write_vals['phone'] = values['phone']
        if values.get('email'):
            write_vals['email_from'] = values['email']
        if values.get('emergency_contact_name'):
            write_vals['x_studio_emergency_contact_name'] = values['emergency_contact_name']
        if values.get('emergency_contact_phone'):
            write_vals['x_studio_emergency_contact_phone'] = values['emergency_contact_phone']
        if values.get('emergency_contact_relationship'):
            write_vals['x_studio_emergency_contact_relationship'] = values['emergency_contact_relationship']

        # Section 2 — Funding / Payer
        if values.get('payer_type'):
            write_vals['x_studio_payer_type'] = values['payer_type']
        if values.get('referral_date'):
            write_vals['x_studio_referral_date'] = values['referral_date']
        if values.get('claim_reference'):
            write_vals['x_studio_claim_reference_'] = values['claim_reference']
        if values.get('case_manager_name'):
            write_vals['x_studio_case_manager_name'] = values['case_manager_name']
        if values.get('case_manager_phone'):
            write_vals['x_studio_case_manager_phone'] = values['case_manager_phone']
        if values.get('case_manager_email'):
            write_vals['x_studio_case_manager_email'] = values['case_manager_email']

        # Section 3 — Services
        if values.get('service_types'):
            service_ids = []
            for name in values['service_types']:
                rec = self.env['x_lead_service_types'].sudo().search(
                    [('x_name', '=', name)], limit=1)
                if rec:
                    service_ids.append(rec.id)
            if service_ids:
                write_vals['x_studio_service_types'] = [(6, 0, service_ids)]
        if values.get('service_description'):
            write_vals['x_studio_service_description'] = values['service_description']
        if values.get('authorized_hours_week'):
            write_vals['x_studio_authorized_hoursweek'] = float(values['authorized_hours_week'])

        # Section 4 — Schedule
        if values.get('desired_start_date'):
            write_vals['x_studio_desired_start_date'] = values['desired_start_date']
        if values.get('estimated_hours_week'):
            write_vals['x_studio_estimated_hoursweek'] = float(values['estimated_hours_week'])
        if values.get('preferred_days'):
            day_ids = []
            for name in values['preferred_days']:
                rec = self.env['x_lead_preferred_days'].sudo().search(
                    [('x_name', '=', name)], limit=1)
                if rec:
                    day_ids.append(rec.id)
            if day_ids:
                write_vals['x_studio_preferred_days'] = [(6, 0, day_ids)]
        if values.get('preferred_time_of_day'):
            write_vals['x_studio_preferred_time_of_day'] = values['preferred_time_of_day']

        # Section 5 — Care Considerations
        if values.get('mobility_needs'):
            write_vals['x_studio_mobility_needs'] = values['mobility_needs']
        if values.get('allergies'):
            write_vals['x_studio_allergies_medical_conditions'] = values['allergies']
        if values.get('medications'):
            write_vals['x_studio_medications'] = values['medications']
        if values.get('caregiver_gender_preference'):
            write_vals['x_studio_caregiver_gender_preference'] = values['caregiver_gender_preference']
        if values.get('language_preference'):
            write_vals['x_studio_language_preference'] = values['language_preference']
        if values.get('pets_in_home'):
            write_vals['x_studio_pets_in_home'] = values['pets_in_home']
        if values.get('access_instructions'):
            write_vals['x_studio_access_instructions'] = values['access_instructions']

        # Section 6 — Care Team
        if values.get('physician_name'):
            write_vals['x_studio_physician_name'] = values['physician_name']
        if values.get('physician_phone'):
            write_vals['x_studio_physician_phone'] = values['physician_phone']
        if values.get('ot_name'):
            write_vals['x_studio_ot_name'] = values['ot_name']
        if values.get('ot_phone'):
            write_vals['x_studio_ot_phone'] = values['ot_phone']

        # Section 7 — Consent
        if values.get('consent_contact'):
            write_vals['x_studio_consent_contact_by_phoneemail'] = True

        # Mark submitted
        write_vals['x_intake_submitted'] = True
        write_vals['x_intake_submitted_date'] = fields.Datetime.now()

        # Write to lead
        lead.write(write_vals)

        # Sync to partner — so profile tab on contact is populated
        lead._sync_to_partner(write_vals)

        # Also sync phone/email to partner directly
        if lead.partner_id:
            partner_basic = {}
            if values.get('phone'):
                partner_basic['phone'] = values['phone']
            if values.get('email'):
                partner_basic['email'] = values['email']
            if partner_basic:
                lead.partner_id.sudo().write(partner_basic)

        lead.message_post(
            body="✅ <b>Client Intake Form submitted</b> via the online link.",
            subtype_xmlid='mail.mt_note',
        )
        return {'status': 'ok'}
