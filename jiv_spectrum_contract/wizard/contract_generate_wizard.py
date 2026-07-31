import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class JivContractGenerateWizard(models.TransientModel):
    _name = 'jiv.contract.generate.wizard'
    _description = 'Generate Client Service Agreement'

    lead_id = fields.Many2one('crm.lead', required=True, readonly=True)

    # ── Editable contract fields ─────────────────────────────────────────────
    client_name = fields.Char(string='Client / Care Recipient Full Name', required=True)
    payer = fields.Char(string='Payer (if different from Client)')
    service_type = fields.Char(string='Service Type(s)')
    authorized_hours_week = fields.Float(string='Authorized Hours/Week')
    service_rate = fields.Float(string='Rate ($/hr or $/day)')
    monthly_budget = fields.Float(string='Monthly Authorized Budget')
    budget_expiry_date = fields.Date(string='Authorization Expiry Date')
    start_date = fields.Date(string='Start Date')
    preferred_days = fields.Char(string='Preferred Days / Times')
    notice_days = fields.Integer(string='Notice Period (days)', default=14)
    billing_contact_name = fields.Char(string='Billing Contact Name')
    billing_contact_email = fields.Char(string='Billing Contact Email')
    case_manager_name = fields.Char(string='Case Manager Name')
    case_manager_phone = fields.Char(string='Case Manager Phone')

    def action_confirm(self):
        """Generate the PDF contract and attach it to the lead."""
        self.ensure_one()
        lead = self.lead_id

        # Render PDF
        report = self.env.ref('jiv_spectrum_contract.action_report_contract')
        pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            report, res_ids=self.ids)

        # Attach to lead
        filename = f"CSA_{lead.partner_id.name or lead.name}_{fields.Date.today()}.pdf"
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'type': 'binary',
            'datas': pdf_content if isinstance(pdf_content, str)
                     else pdf_content if isinstance(pdf_content, bytes)
                     else pdf_content,
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'mimetype': 'application/pdf',
        })

        import base64
        attachment.write({'datas': base64.b64encode(pdf_content)})

        # Mint a contract token for the sign URL
        if not lead.x_contract_token:
            lead.x_contract_token = uuid.uuid4().hex

        lead.write({
            'x_contract_state': 'generated',
            'x_contract_attachment_id': attachment.id,
        })

        lead.message_post(
            body=f'📄 <b>Client Service Agreement generated</b>: '
                 f'<a href="/web/content/{attachment.id}?download=true">'
                 f'{filename}</a>',
            subtype_xmlid='mail.mt_note',
            attachment_ids=[attachment.id],
        )

        return {'type': 'ir.actions.act_window_close'}
