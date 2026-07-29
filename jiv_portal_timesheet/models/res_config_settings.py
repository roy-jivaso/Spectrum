from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    jiv_auto_create_employee = fields.Boolean(
        string='Auto-create Employee for Portal Users',
        config_parameter='jiv_portal_timesheet.auto_create_employee',
        help='Create an hr.employee automatically the first time a portal '
             'collaborator logs time. Leave off to require the manager to '
             'create the employee record explicitly.',
    )
    jiv_portal_employee_department_id = fields.Many2one(
        'hr.department',
        string='Department for Portal Employees',
        help='Department assigned to auto-created portal employees. Using a '
             'dedicated department keeps them out of internal HR reporting.',
    )
    jiv_portal_backdate_days = fields.Integer(
        string='Allowed Back-dating (days)',
        default=7,
        config_parameter='jiv_portal_timesheet.backdate_days',
        help='How many days in the past a portal user may log time. '
             'Set to 0 to allow today only, or -1 to disable the check.',
    )
    jiv_portal_max_hours = fields.Float(
        string='Max Hours per Entry',
        default=24.0,
        config_parameter='jiv_portal_timesheet.max_hours_per_line',
    )
    jiv_portal_require_approval = fields.Boolean(
        string='Require Approval of Portal Timesheets',
        default=True,
        config_parameter='jiv_portal_timesheet.require_approval',
        help='Portal entries are created as "To Approve" and can be '
             'excluded from invoicing until an approver validates them.',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        dept_id = ICP.get_param(
            'jiv_portal_timesheet.employee_department_id')
        res['jiv_portal_employee_department_id'] = int(dept_id) if dept_id else False
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(
            'jiv_portal_timesheet.employee_department_id',
            self.jiv_portal_employee_department_id.id or '')
