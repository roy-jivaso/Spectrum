import logging
from ast import literal_eval

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    jiv_from_portal = fields.Boolean(
        string='Logged from Portal',
        readonly=True,
        copy=False,
        index=True,
        help='Set when the record was created by a portal user from the '
             'portal Attendances page. Use it to exclude external '
             'collaborators from internal HR reporting.',
    )

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    def _jiv_check_portal_own(self):
        """Portal users may only touch their own records."""
        if not self.env.user._is_portal():
            return
        for rec in self:
            if rec.employee_id.user_id != self.env.user:
                raise AccessError(_(
                    'You can only access your own attendance records.'))

    def write(self, vals):
        # hr_attendance recomputes worked_hours / overtime after
        # check_out is set, in whatever environment made the change.
        # Skip the portal field restriction for that internal pass.
        if self.env.user._is_portal() and not self.env.context.get(
                'jiv_skip_portal_field_check'):
            self._jiv_check_portal_own()
            allowed = {'check_out'}
            forbidden = set(vals) - allowed
            if forbidden:
                raise AccessError(_(
                    'You are not allowed to modify: %s',
                    ', '.join(sorted(forbidden))))
        return super().write(vals)

    def unlink(self):
        if self.env.user._is_portal():
            raise UserError(_(
                'Attendance records cannot be deleted. Please contact '
                'your administrator if an entry is wrong.'))
        return super().unlink()

    # ------------------------------------------------------------------
    # Portal check in / out
    # ------------------------------------------------------------------
    @api.model
    def _jiv_get_open_attendance(self, employee):
        """The employee's currently open (not checked out) record."""
        return self.sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], order='check_in desc', limit=1)

    # Studio field on hr.attendance linking the shift to a client.
    # Guarded everywhere: the module must still work on databases where
    # this field was never created.
    JIV_RECIPIENT_FIELD = 'x_studio_client_care_recipient'

    @api.model
    def _jiv_has_recipient_field(self):
        return self.JIV_RECIPIENT_FIELD in self._fields

    @api.model
    def _jiv_recipient_options(self):
        """Partners a portal user may pick as care recipient.

        Domain is configurable because 'who counts as a client' differs
        per database. Default is customers only - without a domain this
        would expose every partner in the system to portal users.
        """
        if not self._jiv_has_recipient_field():
            return self.env['res.partner']
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('jiv_portal_attendance.recipient_domain')
        try:
            domain = literal_eval(raw) if raw else [('customer_rank', '>', 0)]
        except (ValueError, SyntaxError):
            _logger.warning(
                'Invalid jiv_portal_attendance.recipient_domain, '
                'falling back to customers only')
            domain = [('customer_rank', '>', 0)]
        return self.env['res.partner'].sudo().search(domain, order='name')

    @api.model
    def jiv_portal_check_in(self, recipient_id=None):
        """Open a new attendance for the current portal user."""
        if not self.env.user._jiv_can_use_portal_attendance():
            raise AccessError(_(
                'You are not allowed to record attendance.'))
        employee = self.env.user._jiv_get_attendance_employee()
        if self._jiv_get_open_attendance(employee):
            raise UserError(_(
                'You are already checked in. Please check out first.'))

        vals = {
            'employee_id': employee.id,
            'check_in': fields.Datetime.now(),
            'jiv_from_portal': True,
        }

        if self._jiv_has_recipient_field():
            if not recipient_id:
                raise UserError(_(
                    'Please select a client before checking in.'))
            # Validate against the allowed list rather than trusting the
            # posted id - the form is client-side and can be tampered with.
            allowed = self._jiv_recipient_options()
            if int(recipient_id) not in allowed.ids:
                raise AccessError(_(
                    'That client is not available for selection.'))
            vals[self.JIV_RECIPIENT_FIELD] = int(recipient_id)

        return self.sudo().create(vals)

    @api.model
    def jiv_portal_check_out(self):
        """Close the open attendance for the current portal user."""
        if not self.env.user._jiv_can_use_portal_attendance():
            raise AccessError(_(
                'You are not allowed to record attendance.'))
        employee = self.env.user._jiv_get_attendance_employee()
        attendance = self._jiv_get_open_attendance(employee)
        if not attendance:
            raise UserError(_(
                'You are not checked in, so there is nothing to close.'))
        attendance.with_context(
            jiv_skip_portal_field_check=True,
        ).write({'check_out': fields.Datetime.now()})
        return attendance