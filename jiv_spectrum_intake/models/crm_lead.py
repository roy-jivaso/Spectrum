import uuid
from odoo import models, fields, api


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # Unique token so the public form URL is unguessable
    x_intake_token = fields.Char(
        string='Intake Token',
        copy=False,
        readonly=True,
        index=True,
    )
    x_intake_submitted = fields.Boolean(
        string='Intake Form Submitted',
        default=False,
        copy=False,
        readonly=True,
    )
    x_intake_submitted_date = fields.Datetime(
        string='Intake Submitted On',
        copy=False,
        readonly=True,
    )

    def _get_or_create_intake_token(self):
        """Return existing token or mint a new one."""
        self.ensure_one()
        if not self.x_intake_token:
            self.x_intake_token = uuid.uuid4().hex
        return self.x_intake_token

    def action_send_intake_form(self):
        """Open the Send Intake Form dialog."""
        self.ensure_one()
        self._get_or_create_intake_token()

        template = self.env.ref(
            'jiv_spectrum_intake.email_template_intake_form', raise_if_not_found=False)

        # Build default recipient: partner email or email_from
        default_email = (
            self.partner_id.email or self.email_from or ''
        )
        default_name = (
            self.partner_id.name or self.partner_name or self.contact_name or ''
        )

        ctx = {
            'default_model': 'crm.lead',
            'default_res_ids': self.ids,
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'default_partner_ids': self.partner_id.ids if self.partner_id else [],
            'default_email_to': default_email,
            'default_email_from': self.env.user.email_formatted,
            'force_email': True,
            # Pass through so the dialog JS can show the link
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

    @api.model
    def submit_intake_form(self, token, values):
        """
        Called by the website controller on form submission.
        Finds the lead by token and writes all intake values.
        Returns dict with status.
        """
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

        # Section 3 — Services (many2many by x_name)
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

        lead.write(write_vals)

        # Post chatter message
        lead.message_post(
            body="✅Client Intake Form submitted via the online link.",
            subtype_xmlid='mail.mt_note',
        )

        return {'status': 'ok'}
