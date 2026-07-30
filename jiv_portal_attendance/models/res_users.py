from odoo import _, models
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _jiv_can_use_portal_attendance(self):
        """Whether this user may check in from the portal.

        Unrestricted by default. When restrict_group is enabled, only
        users in the Portal Attendance group qualify - useful when the
        database also has portal customers who have no business clocking
        in.
        """
        self.ensure_one()
        if not self.env['ir.config_parameter'].sudo().get_param(
                'jiv_portal_attendance.restrict_group'):
            return True
        return self.has_group('jiv_portal_attendance.group_portal_attendance')

    def _jiv_get_attendance_employee(self, company=None):
        """Return the hr.employee to attach portal attendance to.

        hr.attendance requires an employee and portal users normally have
        none, so either auto-provision one or refuse clearly.
        """
        self.ensure_one()
        company = company or self.env.company
        Employee = self.env['hr.employee'].sudo()
        employee = Employee.search([
            ('user_id', '=', self.id),
            ('company_id', '=', company.id),
        ], limit=1)
        if employee:
            return employee

        ICP = self.env['ir.config_parameter'].sudo()
        if not ICP.get_param('jiv_portal_attendance.auto_create_employee'):
            raise UserError(_(
                'No employee record is linked to your account, so '
                'attendance cannot be recorded. Please contact your '
                'administrator.'))

        vals = {
            'name': self.partner_id.name or self.name,
            'user_id': self.id,
            'work_email': self.email,
            'company_id': company.id,
        }
        dept_id = ICP.get_param('jiv_portal_attendance.employee_department_id')
        if dept_id:
            department = self.env['hr.department'].sudo().browse(int(dept_id))
            if department.exists():
                vals['department_id'] = department.id
        return Employee.create(vals)

    def _jiv_portal_attendance_state(self):
        """(is_checked_in, open_attendance) for the current user."""
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        employee = Employee.search([('user_id', '=', self.id)], limit=1)
        if not employee:
            return False, self.env['hr.attendance']
        attendance = self.env['hr.attendance']._jiv_get_open_attendance(
            employee)
        return bool(attendance), attendance
