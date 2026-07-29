import logging

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

_logger = logging.getLogger(__name__)


class JivPortalTimesheet(CustomerPortal):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _jiv_get_task(self, task_id, access_token=None):
        """Resolve the task through the standard portal access check.

        ``_document_check_access`` is what enforces the share access token
        and the portal record rules, so it must stay in front of any sudo
        operation.
        """
        return self._document_check_access(
            'project.task', int(task_id), access_token)

    def _jiv_ensure_can_log(self, task):
        project = task.project_id
        if not project._jiv_portal_timesheet_enabled():
            raise AccessError(_(
                'Time logging is not enabled for this project.'))
        # Read access alone is not enough: the collaborator needs Edit.
        # Odoo 18 merged check_access_rights/check_access_rule into
        # check_access; fall back for older builds.
        try:
            if hasattr(task, 'check_access'):
                task.with_user(request.env.user).check_access('write')
            else:  # pragma: no cover - Odoo <= 17
                task.with_user(request.env.user).check_access_rights('write')
                task.with_user(request.env.user).check_access_rule('write')
        except AccessError:
            raise AccessError(_(
                'You have read-only access to this task and cannot log '
                'time on it.'))

    def _jiv_parse_hours(self, raw):
        """Accept both 1.5 and 1:30 style input."""
        raw = (raw or '').strip().replace(',', '.')
        if not raw:
            raise ValidationError(_('Please enter the time spent.'))
        if ':' in raw:
            hours, _sep, minutes = raw.partition(':')
            try:
                return int(hours or 0) + int(minutes or 0) / 60.0
            except ValueError:
                raise ValidationError(
                    _('Invalid time format. Use 1.5 or 1:30.'))
        try:
            return float(raw)
        except ValueError:
            raise ValidationError(
                _('Invalid time format. Use 1.5 or 1:30.'))

    def _jiv_redirect(self, task, access_token=None, error=None, success=None):
        url = '/my/task/%s/timesheets' % task.id
        params = []
        if access_token:
            params.append('access_token=%s' % access_token)
        if error:
            # The message itself travels in the session, not the URL.
            params.append('ts_error=1')
        if success:
            params.append('ts_success=1')
        if params:
            url += '?' + '&'.join(params)
        return request.redirect(url + '#timesheets')

    # ------------------------------------------------------------------
    # Standalone page
    # ------------------------------------------------------------------
    @http.route(['/my/task/<int:task_id>/timesheets'], type='http',
                auth='public', website=True)
    def jiv_portal_task_timesheets(self, task_id, access_token=None, **kw):
        try:
            task_sudo = self._jiv_get_task(task_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        can_log = True
        try:
            self._jiv_ensure_can_log(task_sudo)
        except AccessError:
            can_log = False

        lines = task_sudo.timesheet_ids.filtered(
            lambda l: l.user_id == request.env.user)

        return request.render(
            'jiv_portal_timesheet.jiv_portal_task_timesheets_page', {
                'task': task_sudo,
                'lines': lines.sorted('date', reverse=True),
                'total_hours': sum(lines.mapped('unit_amount')),
                'can_log': can_log,
                'today': fields.Date.context_today(
                    request.env.user).strftime('%Y-%m-%d'),
                'access_token': access_token,
                'page_name': 'task_timesheets',
            })

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    @http.route(['/my/task/<int:task_id>/timesheet/new'], type='http',
                auth='public', website=True, methods=['POST'], csrf=True)
    def jiv_portal_timesheet_create(self, task_id, access_token=None, **post):
        try:
            task_sudo = self._jiv_get_task(task_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        try:
            self._jiv_ensure_can_log(task_sudo)
            unit_amount = self._jiv_parse_hours(post.get('unit_amount'))
            date = post.get('date') or fields.Date.context_today(
                request.env.user)
            employee = request.env.user._jiv_get_timesheet_employee(
                company=task_sudo.company_id)

            require_approval = request.env['ir.config_parameter'].sudo(
            ).get_param('jiv_portal_timesheet.require_approval', 'True')

            vals = {
                'name': (post.get('name') or '').strip() or _('/'),
                'date': date,
                'unit_amount': unit_amount,
                'project_id': task_sudo.project_id.id,
                'task_id': task_sudo.id,
                'employee_id': employee.id,
                'user_id': request.env.user.id,
                'company_id': task_sudo.company_id.id,
                'jiv_from_portal': True,
                'jiv_portal_state': 'draft' if require_approval else 'approved',
            }
            request.env['account.analytic.line'].sudo().create(vals)
        except (UserError, ValidationError, AccessError) as exc:
            request.session['jiv_ts_error'] = str(exc)
            return self._jiv_redirect(task_sudo, access_token, error='1')
        except Exception as exc:
            _logger.exception(
                'Portal timesheet creation failed for task %s', task_id)
            # Show the real cause when the server is in debug/dev mode,
            # otherwise a generic message. Silently swallowing this made
            # configuration errors impossible to diagnose.
            if request.env['ir.config_parameter'].sudo().get_param(
                    'jiv_portal_timesheet.verbose_errors'):
                request.session['jiv_ts_error'] = '%s: %s' % (
                    type(exc).__name__, exc)
            else:
                request.session['jiv_ts_error'] = _(
                    'The entry could not be saved. Please contact the '
                    'project manager.')
            return self._jiv_redirect(task_sudo, access_token, error='1')

        return self._jiv_redirect(task_sudo, access_token, success='1')

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    @http.route(['/my/timesheet/<int:line_id>/edit'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def jiv_portal_timesheet_edit(self, line_id, access_token=None, **post):
        line = request.env['account.analytic.line'].browse(int(line_id))
        try:
            if hasattr(line, 'check_access'):
                line.check_access('write')
            else:  # pragma: no cover - Odoo <= 17
                line.check_access_rights('write')
                line.check_access_rule('write')
            task_sudo = self._jiv_get_task(line.task_id.id, access_token)
            self._jiv_ensure_can_log(task_sudo)
            line.write({
                'name': (post.get('name') or '').strip() or _('/'),
                'date': post.get('date') or line.date,
                'unit_amount': self._jiv_parse_hours(post.get('unit_amount')),
            })
        except (AccessError, MissingError):
            return request.redirect('/my')
        except (UserError, ValidationError) as exc:
            request.session['jiv_ts_error'] = str(exc)
            return self._jiv_redirect(line.task_id, access_token, error='1')
        return self._jiv_redirect(task_sudo, access_token, success='1')

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    @http.route(['/my/timesheet/<int:line_id>/delete'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def jiv_portal_timesheet_delete(self, line_id, access_token=None, **post):
        line = request.env['account.analytic.line'].browse(int(line_id))
        task = line.task_id
        try:
            line.unlink()
        except (AccessError, MissingError):
            return request.redirect('/my')
        except UserError as exc:
            request.session['jiv_ts_error'] = str(exc)
            return self._jiv_redirect(task, access_token, error='1')
        return self._jiv_redirect(task, access_token, success='1')