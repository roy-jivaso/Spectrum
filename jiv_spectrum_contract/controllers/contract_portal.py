import base64
import logging
from io import BytesIO

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class ContractPortalController(http.Controller):

    @http.route('/contract/sign/<string:token>', type='http',
                auth='public', website=True)
    def contract_sign_page(self, token, **kwargs):
        """Render the public contract signing page."""
        lead = request.env['crm.lead'].sudo().search(
            [('x_contract_token', '=', token)], limit=1)

        if not lead or not lead.x_contract_attachment_id:
            return request.render(
                'jiv_spectrum_contract.contract_sign_invalid', {})

        already_signed = lead.x_contract_state == 'signed'

        return request.render('jiv_spectrum_contract.contract_sign_page', {
            'token': token,
            'lead': lead,
            'attachment_id': lead.x_contract_attachment_id.id,
            'already_signed': already_signed,
            'prefill_name': (
                lead.partner_id.name or lead.partner_name or ''),
        })

    @http.route('/contract/sign/submit', type='http',
                auth='public', website=True, methods=['POST'], csrf=True)
    def contract_sign_submit(self, **post):
        """Process the signed agreement submission."""
        token = post.get('token', '')
        lead = request.env['crm.lead'].sudo().search(
            [('x_contract_token', '=', token)], limit=1)

        if not lead:
            return request.render(
                'jiv_spectrum_contract.contract_sign_invalid', {})

        if lead.x_contract_state == 'signed':
            return request.render(
                'jiv_spectrum_contract.contract_sign_thank_you', {})

        signer_name = post.get('signer_name', '').strip()
        signature_data = post.get('signature_data', '')

        try:
            # Build a signed PDF overlay with signature image
            signed_attachment_id = self._create_signed_pdf(
                lead, signer_name, signature_data)

            # Mark lead as signed
            lead.action_mark_signed(signed_attachment_id=signed_attachment_id)

            # Update contract state to sent if it was just generated
            if lead.x_contract_state not in ('signed',):
                lead.write({'x_contract_state': 'signed'})

            # Send confirmation email to client
            self._send_signed_confirmation(lead, signed_attachment_id)

        except Exception:
            _logger.exception(
                'Contract signing failed for lead %s', lead.id)

        return request.render(
            'jiv_spectrum_contract.contract_sign_thank_you', {})

    def _create_signed_pdf(self, lead, signer_name, signature_data):
        """
        Create a signed version of the contract PDF.
        Appends a signature page to the original PDF.
        Returns the new attachment id.
        """
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
        from PyPDF2 import PdfReader, PdfWriter

        original_attachment = lead.x_contract_attachment_id
        original_pdf_bytes = base64.b64decode(original_attachment.datas)

        # Build signature overlay page
        sig_buffer = BytesIO()
        c = rl_canvas.Canvas(sig_buffer, pagesize=A4)
        w, h = A4

        c.setFont('Helvetica-Bold', 14)
        c.drawString(60, h - 60, 'DIGITALLY SIGNED')
        c.setFont('Helvetica', 11)
        c.drawString(60, h - 90, f'Signed by: {signer_name}')
        c.drawString(60, h - 110,
                     f'Date: {fields.Datetime.now().strftime("%Y-%m-%d %H:%M UTC")}')
        c.drawString(60, h - 130, 'Document: Client Service Agreement')
        c.drawString(60, h - 150, f'Reference: {lead.x_contract_token}')

        # Draw signature image
        if signature_data and signature_data.startswith('data:image/png;base64,'):
            try:
                from reportlab.lib.utils import ImageReader
                from PIL import Image
                img_data = base64.b64decode(
                    signature_data.split(',', 1)[1])
                img = Image.open(BytesIO(img_data))
                img_reader = ImageReader(BytesIO(img_data))
                c.drawImage(img_reader, 60, h - 320, width=300, height=120,
                            preserveAspectRatio=True, mask='auto')
            except Exception:
                _logger.warning('Could not render signature image', exc_info=True)

        c.line(60, h - 330, 360, h - 330)
        c.setFont('Helvetica', 9)
        c.drawString(60, h - 345, 'Client / Guardian Signature')
        c.save()
        sig_buffer.seek(0)

        # Merge original PDF + signature page
        reader = PdfReader(BytesIO(original_pdf_bytes))
        sig_reader = PdfReader(sig_buffer)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)
        for page in sig_reader.pages:
            writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        signed_bytes = output.getvalue()

        filename = f"SIGNED_CSA_{lead.partner_id.name or lead.name}_{fields.Date.today()}.pdf"
        attachment = request.env['ir.attachment'].sudo().create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(signed_bytes),
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'mimetype': 'application/pdf',
        })
        return attachment.id

    def _send_signed_confirmation(self, lead, signed_attachment_id):
        """Email the signed copy back to the client."""
        if not (lead.partner_id.email or lead.email_from):
            return
        try:
            request.env['mail.mail'].sudo().create({
                'subject': 'Your Signed Client Service Agreement — Spectrum Home & Family Care',
                'email_from': request.env.company.email or 'noreply@spectrumcares.com',
                'email_to': lead.partner_id.email or lead.email_from,
                'body_html': f'''
                    <p>Dear {lead.partner_id.name or 'Client'},</p>
                    <p>Thank you for signing your Client Service Agreement.
                    Please find your signed copy attached for your records.</p>
                    <p>Spectrum Home &amp; Family Care</p>
                ''',
                'attachment_ids': [(4, signed_attachment_id)],
            }).send()
        except Exception:
            _logger.warning(
                'Could not send signed confirmation email', exc_info=True)
