from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    jiv_allow_portal_timesheet = fields.Boolean(
        string='Portal Timesheet Entry',
        default=False,
        help='Allow portal collaborators with Edit access to log their own '
             'time on the tasks of this project. Requires Timesheets to be '
             'enabled on the project and the project visibility to be '
             '"Invited portal users and all internal users".',
    )

    def _jiv_portal_timesheet_enabled(self):
        """True when this project accepts portal timesheet entries."""
        self.ensure_one()
        # 'allow_timesheets' comes from hr_timesheet; guard in case the
        # field is absent or renamed on a given build.
        timesheets_on = getattr(self, 'allow_timesheets', True)
        return bool(
            self.jiv_allow_portal_timesheet
            and timesheets_on
            and self.privacy_visibility == 'portal'
        )
