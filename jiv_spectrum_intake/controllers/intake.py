import json
from odoo import http
from odoo.http import request


class IntakeFormController(http.Controller):

    @http.route('/intake/<string:token>', type='http', auth='public', website=True)
    def intake_form(self, token, **kwargs):
        """Render the public intake form."""
        lead = request.env['crm.lead'].sudo().search(
            [('x_intake_token', '=', token)], limit=1)

        if not lead:
            return request.render('jiv_spectrum_intake.intake_invalid', {})

        if lead.x_intake_submitted:
            return request.render('jiv_spectrum_intake.intake_already_submitted', {})

        # Pre-fill what we already know
        prefill = {
            'name': lead.partner_id.name or lead.partner_name or lead.contact_name or '',
            'phone': lead.phone or lead.mobile or '',
            'email': lead.partner_id.email or lead.email_from or '',
        }

        # Available options from Studio custom models
        service_types = request.env['x_lead_service_types'].sudo().search([])
        preferred_days = request.env['x_lead_preferred_days'].sudo().search([])

        return request.render('jiv_spectrum_intake.intake_form_page', {
            'token': token,
            'lead': lead,
            'prefill': prefill,
            'service_types': service_types,
            'preferred_days': preferred_days,
        })

    @http.route('/intake/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def intake_submit(self, **post):
        """Handle intake form submission."""
        token = post.get('token', '')

        # Collect multi-value checkboxes
        service_types = request.httprequest.form.getlist('service_types')
        preferred_days = request.httprequest.form.getlist('preferred_days')

        values = {
            'date_of_birth': post.get('date_of_birth') or False,
            'phone': post.get('phone') or False,
            'email': post.get('email') or False,
            'emergency_contact_name': post.get('emergency_contact_name') or False,
            'emergency_contact_phone': post.get('emergency_contact_phone') or False,
            'emergency_contact_relationship': post.get('emergency_contact_relationship') or False,
            'payer_type': post.get('payer_type') or False,
            'referral_date': post.get('referral_date') or False,
            'claim_reference': post.get('claim_reference') or False,
            'case_manager_name': post.get('case_manager_name') or False,
            'case_manager_phone': post.get('case_manager_phone') or False,
            'case_manager_email': post.get('case_manager_email') or False,
            'service_types': service_types,
            'service_description': post.get('service_description') or False,
            'authorized_hours_week': post.get('authorized_hours_week') or False,
            'desired_start_date': post.get('desired_start_date') or False,
            'estimated_hours_week': post.get('estimated_hours_week') or False,
            'preferred_days': preferred_days,
            'preferred_time_of_day': post.get('preferred_time_of_day') or False,
            'mobility_needs': post.get('mobility_needs') or False,
            'allergies': post.get('allergies') or False,
            'medications': post.get('medications') or False,
            'caregiver_gender_preference': post.get('caregiver_gender_preference') or False,
            'language_preference': post.get('language_preference') or False,
            'pets_in_home': post.get('pets_in_home') or False,
            'access_instructions': post.get('access_instructions') or False,
            'physician_name': post.get('physician_name') or False,
            'physician_phone': post.get('physician_phone') or False,
            'ot_name': post.get('ot_name') or False,
            'ot_phone': post.get('ot_phone') or False,
            'consent_contact': bool(post.get('consent_contact')),
        }

        result = request.env['crm.lead'].sudo().submit_intake_form(token, values)

        if result.get('status') == 'ok':
            return request.render('jiv_spectrum_intake.intake_thank_you', {})
        else:
            return request.render('jiv_spectrum_intake.intake_invalid', {})
