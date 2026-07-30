from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    jiv_att_auto_create_employee = fields.Boolean(
        string='Auto-create Employee for Portal Users',
        config_parameter='jiv_portal_attendance.auto_create_employee',
        help='Create an hr.employee automatically the first time a portal '
             'user checks in. Turn this off to require an administrator to '
             'create the employee record deliberately - the user then gets '
             'a clear message instead of an unexpected HR record.',
    )
    jiv_att_employee_department_id = fields.Many2one(
        'hr.department',
        string='Department for Portal Employees',
        help='Department assigned to auto-created portal employees. Using a '
             'dedicated department keeps external collaborators out of your '
             'internal org chart and HR reporting.',
    )
    jiv_att_checkin_on_login = fields.Boolean(
        string='Check In Automatically on Login',
        config_parameter='jiv_portal_attendance.checkin_on_login',
        help='Create a checked-in attendance whenever a portal user logs in '
             'without an open record. Off by default: this records time the '
             'user never initiated (a late-night login to read a message '
             'becomes a shift) and it feeds worked hours and overtime.',
    )
    jiv_att_restrict_group = fields.Boolean(
        string='Restrict to Selected Users',
        config_parameter='jiv_portal_attendance.restrict_group',
        help='When enabled, only portal users in the "Portal Attendance" '
             'group see the Attendances card and can check in. Otherwise '
             'every portal user on this database can - including customers '
             'on unrelated projects.',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        dept_id = self.env['ir.config_parameter'].sudo().get_param(
            'jiv_portal_attendance.employee_department_id')
        res['jiv_att_employee_department_id'] = int(dept_id) if dept_id else False
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'jiv_portal_attendance.employee_department_id',
            self.jiv_att_employee_department_id.id or '')
