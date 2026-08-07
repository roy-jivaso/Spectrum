import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        return vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(
            grouped=grouped, final=final, date=date
        )
        for move in moves:
            self._jiv_add_client_sections(move)
        return moves

    def _jiv_add_client_sections(self, move):
        """Insert a section line naming the client above each SO block."""
        AML = self.env['account.move.line']
        lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        seen = set()
        seq = 0
        new_lines = []
        for line in lines.sorted(lambda l: (l.sale_line_ids[:1].order_id.id, l.id)):
            order = line.sale_line_ids[:1].order_id
            if order and order.id not in seen:
                seen.add(order.id)
                seq += 1
                new_lines.append((0, 0, {
                    'display_type': 'line_section',
                    'name': self._jiv_section_label(order),
                    'sequence': seq,
                }))
            seq += 1
            new_lines.append((1, line.id, {'sequence': seq}))
        if new_lines:
            move.write({'invoice_line_ids': new_lines})

    def _jiv_section_label(self, order):
        client = order.partner_id.name
        return f"{client} — {order.name}"
class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ── Contract state tracking ──────────────────────────────────────────────
    x_contract_state = fields.Selection([
        ('draft',  'Not Generated'),
        ('generated', 'Generated'),
        ('sent',   'Sent'),
        ('signed', 'Signed'),
    ], string='Contract Status', default='draft', copy=False, readonly=True)

    x_contract_token = fields.Char(
        string='Contract Token', copy=False, readonly=True, index=True)

    x_contract_attachment_id = fields.Many2one(
        'ir.attachment', string='Generated Contract', copy=False, readonly=True)

    x_sign_request_id = fields.Many2one(
        'sign.request', string='Sign Request', copy=False, readonly=True)

    x_contract_signed_date = fields.Datetime(
        string='Signed On', copy=False, readonly=True)

    # ── Actions ─────────────────────────────────────────────────────────────
    def action_generate_contract(self):
        """Open the Generate Contract wizard."""
        self.ensure_one()
        if self.type != 'opportunity':
            raise UserError(_('Contracts can only be generated for Opportunities.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate Client Service Agreement'),
            'res_model': 'jiv.contract.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_id': self.id,
                'default_client_name': (
                    self.partner_id.name or self.partner_name or ''),
                'default_payer': self._get_payer_label(),
                'default_service_type': self._get_service_types_label(),
                'default_authorized_hours_week': self.x_studio_authorized_hoursweek or 0,
                'default_service_rate': self.x_studio_service_rate or 0,
                'default_monthly_budget': self.x_studio_monthly_authorized_budget or 0,
                'default_budget_expiry_date': self.x_studio_budgetauthorization_expiry_date,
                'default_start_date': self.x_studio_desired_start_date,
                'default_preferred_days': self._get_preferred_days_label(),
                'default_billing_contact_name': (
                    self.partner_id.name or ''),
                'default_billing_contact_email': (
                    self.partner_id.email or self.email_from or ''),
                'default_case_manager_name': self.x_studio_case_manager_name or '',
                'default_case_manager_phone': self.x_studio_case_manager_phone or '',
                'default_notice_days': 14,
            },
        }

    def action_send_contract(self):
        """Open email compose to send the contract link."""
        self.ensure_one()
        if self.x_contract_state == 'draft':
            raise UserError(_(
                'Please generate the contract first before sending.'))
        if not self.x_contract_token:
            self.x_contract_token = uuid.uuid4().hex

        template = self.env.ref(
            'jiv_spectrum_contract.email_template_contract',
            raise_if_not_found=False)
        ctx = {
            'default_model': 'crm.lead',
            'default_res_ids': self.ids,
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'default_partner_ids': self.partner_id.ids if self.partner_id else [],
            'default_email_to': (
                self.partner_id.email or self.email_from or ''),
            'default_attachment_ids': (
                [self.x_contract_attachment_id.id]
                if self.x_contract_attachment_id else []),
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Contract'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def _get_payer_label(self):
        if not self.x_studio_payer_type:
            return ''
        field = self.env['ir.model.fields'].sudo().search([
            ('model', '=', 'crm.lead'),
            ('name', '=', 'x_studio_payer_type'),
        ], limit=1)
        for sel in field.selection_ids:
            if sel.value == self.x_studio_payer_type:
                return sel.name
        return self.x_studio_payer_type

    def _get_service_types_label(self):
        if not self.x_studio_service_types:
            return ''
        return ', '.join(self.x_studio_service_types.mapped('x_name'))

    def _get_preferred_days_label(self):
        if not self.x_studio_preferred_days:
            return ''
        return ', '.join(self.x_studio_preferred_days.mapped('x_name'))

    def _get_contract_url(self):
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base}/contract/sign/{self.x_contract_token}"

    def action_mark_signed(self, signed_attachment_id=None):
        """Called by the portal controller when client signs."""
        self.ensure_one()
        vals = {
            'x_contract_state': 'signed',
            'x_contract_signed_date': fields.Datetime.now(),
        }
        self.write(vals)
        body = "✅Client Service Agreement signed by the client via the online portal."
        if signed_attachment_id:
            body += f' <a href="/web/content/{signed_attachment_id}">Download signed copy</a>'
        self.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
            attachment_ids=[signed_attachment_id] if signed_attachment_id else [],
        )
