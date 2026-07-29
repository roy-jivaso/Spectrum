from odoo import _, models
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _jiv_get_timesheet_employee(self, company=None):
        """Return the hr.employee to bill portal time against.

        hr_timesheet's ``_check_employee_id`` constraint refuses any
        analytic line without an employee, and portal users normally have
        none. Depending on configuration we either auto-provision one or
        raise so the project manager creates it deliberately.
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
        if not ICP.get_param('jiv_portal_timesheet.auto_create_employee'):
            raise UserError(_(
                'No employee record is linked to your user account, so '
                'time cannot be recorded. Please ask the project manager '
                'to set one up for you.'))

        dept_id = ICP.get_param('jiv_portal_timesheet.employee_department_id')
        vals = {
            'name': self.partner_id.name or self.name,
            'user_id': self.id,
            'work_email': self.email,
            'company_id': company.id,
        }
        if dept_id:
            department = self.env['hr.department'].sudo().browse(int(dept_id))
            if department.exists():
                vals['department_id'] = department.id
        return Employee.create(vals)
