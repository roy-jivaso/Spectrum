from odoo import _, fields, models


class HrAttendancePortalMixin(models.Model):
    """Give hr.attendance a chatter and a portal URL.

    hr.attendance has neither by default. Adding mail.thread creates the
    message/follower columns on the table, and portal.mixin adds
    access_token - both are schema changes to a core model, so this
    module cannot be uninstalled cleanly without leaving them behind.
    """
    _name = 'hr.attendance'
    _inherit = ['hr.attendance', 'mail.thread', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for record in self:
            record.access_url = '/my/attendance/%s' % record.id

    def _get_portal_return_action(self):
        self.ensure_one()
        return self.env.ref('hr_attendance.hr_attendance_action')

    def _message_get_suggested_recipients(self, *args, **kwargs):
        # Signature moved between versions; stay permissive rather than
        # breaking chatter on a mismatch.
        try:
            return super()._message_get_suggested_recipients(*args, **kwargs)
        except TypeError:
            return []

    def _jiv_portal_message_post_hook(self):
        """Notify the employee's manager when a portal user writes in."""
        self.ensure_one()
        manager = self.employee_id.parent_id.user_id
        if manager:
            self.message_subscribe(partner_ids=manager.partner_id.ids)
