from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    jiv_from_portal = fields.Boolean(
        string='Logged from Portal',
        readonly=True,
        copy=False,
        index=True,
        help='Set automatically when the line is created by a portal '
             'collaborator from the portal task page.',
    )
    jiv_portal_state = fields.Selection(
        selection=[
            ('draft', 'To Approve'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
        ],
        string='Approval',
        copy=False,
        index=True,
        help='Approval state for portal-submitted timesheets. Internal '
             'timesheets are left empty and behave as before.',
    )
    jiv_approved_by_id = fields.Many2one(
        'res.users', string='Approved By', readonly=True, copy=False)
    jiv_approved_on = fields.Datetime(
        string='Approved On', readonly=True, copy=False)
    jiv_refusal_reason = fields.Char(
        string='Refusal Reason', copy=False)

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    @api.constrains('unit_amount')
    def _jiv_check_portal_hours(self):
        """Keep portal submissions within a sane range.

        Without this a fat-fingered entry of 800 instead of 8.00 flows
        straight into analytic reporting.
        """
        max_hours = float(self.env['ir.config_parameter'].sudo().get_param(
            'jiv_portal_timesheet.max_hours_per_line', 24.0))
        for line in self:
            if not line.jiv_from_portal:
                continue
            if line.unit_amount <= 0:
                raise ValidationError(
                    _('Please enter a number of hours greater than zero.'))
            if line.unit_amount > max_hours:
                raise ValidationError(_(
                    'A single timesheet entry cannot exceed %(max)s hours. '
                    'Please split it across several lines.',
                    max=max_hours,
                ))

    @api.constrains('date')
    def _jiv_check_portal_date(self):
        """Block back-dating beyond the configured window."""
        ICP = self.env['ir.config_parameter'].sudo()
        window = int(ICP.get_param(
            'jiv_portal_timesheet.backdate_days', 7))
        today = fields.Date.context_today(self)
        for line in self:
            if not line.jiv_from_portal or not line.date:
                continue
            if line.date > today:
                raise ValidationError(
                    _('Timesheets cannot be logged for a future date.'))
            if window >= 0 and (today - line.date).days > window:
                raise ValidationError(_(
                    'Timesheets can only be logged up to %(days)s days in '
                    'the past. Please contact the project manager.',
                    days=window,
                ))

    def _jiv_check_portal_editable(self):
        """Portal users may only touch their own, still-unapproved lines."""
        if not self.env.user._is_portal():
            return
        for line in self:
            if line.user_id != self.env.user:
                raise AccessError(_(
                    'You can only modify timesheet entries that you '
                    'created yourself.'))
            if line.jiv_portal_state and line.jiv_portal_state != 'draft':
                raise UserError(_(
                    'This entry has already been reviewed and can no '
                    'longer be changed.'))

    def write(self, vals):
        if self.env.user._is_portal():
            self._jiv_check_portal_editable()
            allowed = {'name', 'date', 'unit_amount'}
            forbidden = set(vals) - allowed
            if forbidden:
                raise AccessError(_(
                    'You are not allowed to modify: %s',
                    ', '.join(sorted(forbidden))))
        return super().write(vals)

    def unlink(self):
        if self.env.user._is_portal():
            self._jiv_check_portal_editable()
        return super().unlink()

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------
    def action_jiv_approve(self):
        self._jiv_check_approver()
        self.write({
            'jiv_portal_state': 'approved',
            'jiv_approved_by_id': self.env.user.id,
            'jiv_approved_on': fields.Datetime.now(),
            'jiv_refusal_reason': False,
        })

    def action_jiv_refuse(self):
        self._jiv_check_approver()
        self.write({
            'jiv_portal_state': 'refused',
            'jiv_approved_by_id': self.env.user.id,
            'jiv_approved_on': fields.Datetime.now(),
        })

    def action_jiv_reset_draft(self):
        self._jiv_check_approver()
        self.write({
            'jiv_portal_state': 'draft',
            'jiv_approved_by_id': False,
            'jiv_approved_on': False,
        })

    def _jiv_check_approver(self):
        if not self.env.user.has_group('hr_timesheet.group_hr_timesheet_approver'):
            raise AccessError(_(
                'Only timesheet approvers can review portal entries.'))
