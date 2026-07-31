import logging
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager

_logger = logging.getLogger(__name__)

from odoo import _, fields, models


class HrAttendancePortalMixin(models.Model):
    """Give hr.attendance a chatter only.

    portal.mixin removed — it adds access_token and _get_share_url()
    which references fields (date_from) that don't exist on hr.attendance
    in Odoo 19, causing ValueError on every portal page load.
    """
    _name = 'hr.attendance'
    _inherit = ['hr.attendance', 'mail.thread']

    def _message_get_suggested_recipients(self, *args, **kwargs):
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
class JivPortalAttendance(CustomerPortal):

    # ------------------------------------------------------------------
    # My Account counter
    # ------------------------------------------------------------------
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'attendance_count' in counters and \
                request.env.user._jiv_can_use_portal_attendance():
            employee = request.env['hr.employee'].sudo().search(
                [('user_id', '=', request.env.user.id)], limit=1)
            values['attendance_count'] = request.env[
                'hr.attendance'].sudo().search_count(
                    [('employee_id', '=', employee.id)]) if employee else 0
        return values

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _jiv_attendance_domain(self):
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1)
        if not employee:
            return [('id', '=', False)]
        return [('employee_id', '=', employee.id)]

    def _jiv_searchbar_sortings(self):
        return {
            'date':     {'label': _('Date'),     'order': 'check_in desc'},
            'duration': {'label': _('Duration'), 'order': 'worked_hours desc'},
        }

    def _jiv_searchbar_filters(self):
        today = fields.Date.context_today(request.env.user)
        first_of_month = today.replace(day=1)
        quarter_start = today.replace(
            month=((today.month - 1) // 3) * 3 + 1, day=1)
        year_start = today.replace(month=1, day=1)
        week_start = today - timedelta(days=today.weekday())

        user_tz = pytz.timezone(request.env.user.tz or 'UTC')

        def to_utc(day):
            local = user_tz.localize(datetime.combine(day, time.min))
            return fields.Datetime.to_string(
                local.astimezone(pytz.UTC).replace(tzinfo=None))

        def window(start, end=None):
            dom = [('check_in', '>=', to_utc(start))]
            if end:
                dom.append(('check_in', '<', to_utc(end)))
            return dom

        last_month_start = first_of_month - relativedelta(months=1)
        last_week_start = week_start - timedelta(days=7)
        last_year_start = year_start - relativedelta(years=1)

        return {
            'all':          {'label': _('All'),          'domain': [],                                       'sequence': 10},
            'today':        {'label': _('Today'),        'domain': window(today, today + timedelta(days=1)), 'sequence': 20},
            'this_week':    {'label': _('This week'),    'domain': window(week_start),                       'sequence': 30},
            'this_month':   {'label': _('This month'),   'domain': window(first_of_month),                   'sequence': 40},
            'this_quarter': {'label': _('This Quarter'), 'domain': window(quarter_start),                    'sequence': 50},
            'this_year':    {'label': _('This year'),    'domain': window(year_start),                       'sequence': 60},
            'last_week':    {'label': _('Last week'),    'domain': window(last_week_start, week_start),      'sequence': 70},
            'last_month':   {'label': _('Last month'),   'domain': window(last_month_start, first_of_month), 'sequence': 80},
            'last_year':    {'label': _('Last year'),    'domain': window(last_year_start, year_start),      'sequence': 90},
        }

    # ------------------------------------------------------------------
    # Page
    # ------------------------------------------------------------------
    @http.route(['/my/attendances', '/my/attendances/page/<int:page>'],
                type='http', auth='user', website=True)
    def jiv_portal_attendances(self, page=1, sortby='date',
                               filterby='all', search='', search_in='all',
                               **kw):
        if not request.env.user._jiv_can_use_portal_attendance():
            return request.redirect('/my')

        Attendance = request.env['hr.attendance'].sudo()

        sortings = self._jiv_searchbar_sortings()
        filters = self._jiv_searchbar_filters()

        if sortby not in sortings:
            sortby = 'date'
        if filterby not in filters:
            filterby = 'all'

        domain = self._jiv_attendance_domain() + filters[filterby]['domain']

        if search:
            domain += [('check_in', 'ilike', search)]

        total = Attendance.search_count(domain)
        page_detail = pager(
            url='/my/attendances',
            url_args={'sortby': sortby, 'filterby': filterby,
                      'search': search, 'search_in': search_in},
            total=total, page=page, step=self._items_per_page,
        )
        records = Attendance.search(
            domain, order=sortings[sortby]['order'],
            limit=self._items_per_page, offset=page_detail['offset'])

        Att = request.env['hr.attendance']
        needs_recipient = Att._jiv_has_recipient_field()
        recipients = Att._jiv_recipient_options() if needs_recipient \
            else request.env['res.partner']

        return request.render('jiv_portal_attendance.portal_my_attendances', {
            'attendances': records,
            'page_name': 'attendance',
            'pager': page_detail,
            'default_url': '/my/attendances',
            'searchbar_sortings': sortings,
            'sortby': sortby,
            'searchbar_filters': filters,
            'filterby': filterby,
            'search': search,
            'search_in': search_in,
            'needs_recipient': needs_recipient,
            'recipients': recipients,
            'recipient_field': Att.JIV_RECIPIENT_FIELD,
            'notify_type': request.params.get('notify'),
            'notify_message': request.session.pop('jiv_att_message', None),
        })

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------
    @http.route(['/my/attendance/<int:attendance_id>'], type='http',
                auth='user', website=True)
    def jiv_portal_attendance_detail(self, attendance_id, **kw):
        # portal.mixin removed from model so _document_check_access
        # is not available — use plain sudo + own-record check instead
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1)
        if not employee:
            return request.redirect('/my/attendances')

        attendance = request.env['hr.attendance'].sudo().browse(attendance_id)
        if not attendance.exists() or attendance.employee_id != employee:
            return request.redirect('/my/attendances')

        Att = request.env['hr.attendance']
        return request.render(
            'jiv_portal_attendance.portal_attendance_detail', {
                'attendance': attendance,
                'page_name': 'attendance',
                'needs_recipient': Att._jiv_has_recipient_field(),
                'recipient_field': Att.JIV_RECIPIENT_FIELD,
            })

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def _jiv_user_tz(self):
        tz_name = (request.env.user.tz
                   or request.env.context.get('tz')
                   or request.httprequest.cookies.get('tz')
                   or request.env.company.partner_id.tz
                   or 'UTC')
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            _logger.warning('Unknown timezone %r, using UTC', tz_name)
            return pytz.UTC

    def _jiv_local_to_utc(self, value):
        if not value:
            return None
        naive = datetime.strptime(value[:16], '%Y-%m-%dT%H:%M')
        user_tz = self._jiv_user_tz()
        return fields.Datetime.to_string(
            user_tz.localize(naive).astimezone(pytz.UTC).replace(tzinfo=None))

    @http.route(['/my/attendances/new'], type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def jiv_portal_attendance_create(self, check_in=None, check_out=None,
                                     recipient_id=None, **post):
        try:
            request.env['hr.attendance'].jiv_portal_create_attendance(
                check_in=self._jiv_local_to_utc(check_in),
                check_out=self._jiv_local_to_utc(check_out),
                recipient_id=recipient_id or None,
            )
            request.session['jiv_att_message'] = _(
                'Attendance created successfully.')
            notify = 'success'
        except (UserError, AccessError) as exc:
            request.session['jiv_att_message'] = str(exc)
            notify = 'danger'
        except Exception:
            _logger.exception('Portal attendance creation failed for user %s',
                              request.env.user.id)
            request.session['jiv_att_message'] = _(
                'The attendance could not be saved. Please contact your '
                'administrator.')
            notify = 'danger'
        return request.redirect('/my/attendances?notify=%s' % notify)