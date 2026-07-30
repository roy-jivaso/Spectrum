from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


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

    @api.model
    def jiv_portal_check_in(self):
        """Open a new attendance for the current portal user."""
        if not self.env.user._jiv_can_use_portal_attendance():
            raise AccessError(_(
                'You are not allowed to record attendance.'))
        employee = self.env.user._jiv_get_attendance_employee()
        if self._jiv_get_open_attendance(employee):
            raise UserError(_(
                'You are already checked in. Please check out first.'))
        return self.sudo().create({
            'employee_id': employee.id,
            'check_in': fields.Datetime.now(),
            'jiv_from_portal': True,
        })

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
