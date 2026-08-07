import logging
from ast import literal_eval

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'



    jiv_notes = fields.Text(
        string="Notes",
        help="Free-text notes recorded against this attendance entry.",
    )
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
    # Portal attendance creation
    # ------------------------------------------------------------------
    # Studio field on hr.attendance linking the shift to a client.
    # Guarded everywhere: the module must still work on databases where
    # this field was never created.
    JIV_RECIPIENT_FIELD = 'x_studio_client_care_recipient'

    @api.model
    def _jiv_get_open_attendance(self, employee):
        """The employee's currently open (not checked out) record."""
        return self.sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], order='check_in desc', limit=1)

    @api.model
    def _jiv_has_recipient_field(self):
        return self.JIV_RECIPIENT_FIELD in self._fields

    @api.model
    def _jiv_recipient_options(self):
        """Partners a portal user may pick as care recipient.

        Selected by partner tag (res.partner.category_id), which is how
        care recipients are marked on this database - the "Care Recipient"
        tag. Two knobs, in priority order:

          jiv_portal_attendance.recipient_domain  - full domain, wins
          jiv_portal_attendance.recipient_tag     - tag name (default
                                                    "Care Recipient")

        A domain is required one way or the other: without one this
        dropdown would expose every partner on the database - staff,
        vendors, everyone - to portal users.
        """
        if not self._jiv_has_recipient_field():
            return self.env['res.partner']
        ICP = self.env['ir.config_parameter'].sudo()

        raw = ICP.get_param('jiv_portal_attendance.recipient_domain')
        if raw:
            try:
                domain = literal_eval(raw)
            except (ValueError, SyntaxError):
                _logger.warning(
                    'Invalid jiv_portal_attendance.recipient_domain, '
                    'falling back to the tag')
                raw = None
        if not raw:
            tag = ICP.get_param('jiv_portal_attendance.recipient_tag') \
                or 'Care Recipient'
            domain = [('category_id.name', '=', tag)]

        return self.env['res.partner'].sudo().search(domain, order='name')

    @api.model
    def jiv_portal_create_attendance(self, check_in, check_out=None,
                                     recipient_id=None):
        """Create an attendance record on behalf of a portal user.

        Mirrors the backend form: the user supplies the client and both
        datetimes rather than clocking in live.
        """
        if not self.env.user._jiv_can_use_portal_attendance():
            raise AccessError(_(
                'You are not allowed to record attendance.'))
        if not check_in:
            raise UserError(_('Please provide a check in date and time.'))

        employee = self.env.user._jiv_get_attendance_employee()

        vals = {
            'employee_id': employee.id,
            'check_in': check_in,
            'jiv_from_portal': True,
        }
        if check_out:
            vals['check_out'] = check_out

        if self._jiv_has_recipient_field():
            if not recipient_id:
                raise UserError(_(
                    'Please select a client before saving.'))
            # Validate against the allowed list rather than trusting the
            # posted id - the form is client-side and can be tampered with.
            allowed = self._jiv_recipient_options()
            if int(recipient_id) not in allowed.ids:
                raise AccessError(_(
                    'That client is not available for selection.'))
            vals[self.JIV_RECIPIENT_FIELD] = int(recipient_id)

        self._jiv_validate_period(employee, vals['check_in'],
                                  vals.get('check_out'))

        return self.sudo().with_context(
            jiv_skip_portal_field_check=True).create(vals)

    @api.model
    def _jiv_validate_period(self, employee, check_in, check_out=None):
        """Sanity checks a portal user's submitted period."""
        check_in = fields.Datetime.to_datetime(check_in)
        check_out = fields.Datetime.to_datetime(check_out) if check_out \
            else None
        now = fields.Datetime.now()

        if check_in > now:
            raise UserError(_('Check in cannot be in the future.'))
        if check_out:
            if check_out <= check_in:
                raise UserError(_(
                    'Check out must be later than check in.'))
            if check_out > now:
                raise UserError(_('Check out cannot be in the future.'))
            max_hours = float(self.env['ir.config_parameter'].sudo().get_param(
                'jiv_portal_attendance.max_hours_per_record', 24.0))
            hours = (check_out - check_in).total_seconds() / 3600.0
            if hours > max_hours:
                raise UserError(_(
                    'A single attendance cannot exceed %(max)s hours. '
                    'Please split it into separate records.',
                    max=max_hours))

        # Overlapping shifts corrupt worked-hours totals, and hr_attendance
        # only guards this partially for records created via sudo.
        domain = [
            ('employee_id', '=', employee.id),
            ('check_in', '<', fields.Datetime.to_string(check_out or check_in)),
        ]
        if check_out:
            domain += ['|', ('check_out', '=', False),
                       ('check_out', '>', fields.Datetime.to_string(check_in))]
        else:
            domain += [('check_out', '=', False)]
        if self.sudo().search_count(domain):
            raise UserError(_(
                'This period overlaps an attendance you have already '
                'recorded.'))