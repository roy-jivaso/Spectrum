from ast import literal_eval
import logging

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _inherit = ['hr.payslip', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for slip in self:
            slip.access_url = '/my/payslip/%s' % slip.id

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------
    @api.model
    def _jiv_visible_states(self):
        """States an employee may see on the portal.

        Default is confirmed slips only. Draft and 'verify' slips are
        still being worked on by payroll - the numbers move, and showing
        an employee a figure that later changes creates disputes that are
        expensive to unwind.
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'jiv_portal_payslip.visible_states')
        if not raw:
            return ['done', 'paid']
        try:
            states = literal_eval(raw)
            return list(states) if isinstance(states, (list, tuple)) else ['done', 'paid']
        except (ValueError, SyntaxError):
            _logger.warning(
                'Invalid jiv_portal_payslip.visible_states, using done/paid')
            return ['done', 'paid']

    @api.model
    def _jiv_portal_domain(self):
        """Own, confirmed payslips for the current user."""
        employees = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.env.user.id)])
        if not employees:
            return [('id', '=', False)]
        return [
            ('employee_id', 'in', employees.ids),
            ('state', 'in', self._jiv_visible_states()),
        ]

    # ------------------------------------------------------------------
    # Guards - portal access is strictly read-only
    # ------------------------------------------------------------------
    def write(self, vals):
        if self.env.user._is_portal():
            raise AccessError(_(
                'Payslips cannot be modified from the portal.'))
        return super().write(vals)

    def unlink(self):
        if self.env.user._is_portal():
            raise AccessError(_(
                'Payslips cannot be deleted from the portal.'))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._is_portal():
            raise AccessError(_(
                'Payslips cannot be created from the portal.'))
        return super().create(vals_list)
