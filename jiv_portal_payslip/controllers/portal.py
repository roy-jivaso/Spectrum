import logging

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager

_logger = logging.getLogger(__name__)


class JivPortalPayslip(CustomerPortal):

    # ------------------------------------------------------------------
    # My Account
    # ------------------------------------------------------------------
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'payslip_count' in counters:
            Payslip = request.env['hr.payslip']
            values['payslip_count'] = Payslip.sudo().search_count(
                Payslip._jiv_portal_domain())
        return values

    def _jiv_payslip_searchbar_sortings(self):
        """Sort options for the payslip list.

        Prefixed per module on purpose: all CustomerPortal subclasses are
        merged into one class, so a generic helper name here would clash
        with the same name in another portal module.
        """
        return {
            'date': {'label': _('Period'), 'order': 'date_from desc'},
            'name': {'label': _('Reference'), 'order': 'name desc'},
            'state': {'label': _('Status'), 'order': 'state'},
        }

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    @http.route(['/my/payslips', '/my/payslips/page/<int:page>'],
                type='http', auth='user', website=True)
    def jiv_portal_payslips(self, page=1, sortby='date', search='', **kw):
        Payslip = request.env['hr.payslip']
        domain = Payslip._jiv_portal_domain()

        sortings = self._jiv_payslip_searchbar_sortings()
        if sortby not in sortings:
            sortby = 'date'

        if search:
            domain += [('name', 'ilike', search)]

        total = Payslip.sudo().search_count(domain)
        page_detail = pager(
            url='/my/payslips',
            url_args={'sortby': sortby, 'search': search},
            total=total, page=page, step=self._items_per_page,
        )
        slips = Payslip.sudo().search(
            domain, order=sortings[sortby]['order'],
            limit=self._items_per_page, offset=page_detail['offset'])

        return request.render('jiv_portal_payslip.portal_my_payslips', {
            'payslips': slips,
            'page_name': 'payslip',
            'pager': page_detail,
            'default_url': '/my/payslips',
            'searchbar_sortings': sortings,
            'sortby': sortby,
            'search': search,
        })

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------
    def _jiv_get_payslip(self, payslip_id, access_token=None):
        """Resolve a payslip, enforcing ownership and visible state.

        _document_check_access covers the record rule and token, but the
        state filter is applied again here: a rule change or a token
        shared by a manager should not expose a draft slip.
        """
        slip = self._document_check_access(
            'hr.payslip', int(payslip_id), access_token)
        if slip.state not in request.env['hr.payslip']._jiv_visible_states():
            raise AccessError(_('This payslip is not available yet.'))
        return slip

    @http.route(['/my/payslip/<int:payslip_id>'], type='http',
                auth='public', website=True)
    def jiv_portal_payslip_detail(self, payslip_id, access_token=None, **kw):
        try:
            slip_sudo = self._jiv_get_payslip(payslip_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        return request.render('jiv_portal_payslip.portal_payslip_detail', {
            'payslip': slip_sudo,
            'page_name': 'payslip',
            'access_token': access_token,
            'report_type': 'html',
        })

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    @http.route(['/my/payslip/<int:payslip_id>/pdf'], type='http',
                auth='public', website=True)
    def jiv_portal_payslip_pdf(self, payslip_id, access_token=None,
                               download=True, **kw):
        try:
            slip_sudo = self._jiv_get_payslip(payslip_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        report_name = self._jiv_payslip_report_ref()
        if not report_name:
            return request.redirect('/my/payslip/%s' % payslip_id)

        # Render with sudo rather than going through _show_report:
        # ir.actions.report is not readable by base.group_portal, so the
        # portal user gets a 403 on the report lookup itself even though
        # they are entitled to this payslip. Access to the record was
        # already established by _jiv_get_payslip above.
        try:
            pdf, _content_type = request.env['ir.actions.report'].sudo() \
                ._render_qweb_pdf(report_name, res_ids=slip_sudo.ids)
        except Exception:
            _logger.exception(
                'Payslip PDF rendering failed for payslip %s', payslip_id)
            return request.redirect('/my/payslip/%s' % payslip_id)

        filename = '%s.pdf' % (slip_sudo.name or 'payslip').replace('/', '-')
        disposition = 'attachment' if download else 'inline'
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition',
             '%s; filename="%s"' % (disposition, filename)),
        ])

    def _jiv_payslip_report_ref(self):
        """The payslip PDF report_name, if one exists.

        _show_report wants the report_name ('hr_payroll.report_payslip_lang'),
        NOT the action's xml id ('hr_payroll.action_report_payslip').
        Passing the action id produces a 500.

        Every lookup here is sudo'd: env.ref() reads ir.actions.report,
        which base.group_portal cannot read, so an unsudo'd ref() raises
        a 403 before the render is ever reached. Entitlement to the
        payslip itself was already established by the caller.
        """
        Report = request.env['ir.actions.report'].sudo()
        country = (request.env.company.sudo().country_id.code or '')

        preferred = [
            'l10n_%s_hr_payroll.action_report_payslip_%s' % (
                country.lower(), country.lower()),
            'hr_payroll.action_report_payslip',
        ]
        for xid in preferred:
            action = request.env.ref(xid, raise_if_not_found=False)
            action = action.sudo() if action else action
            if action and action.report_name:
                return action.report_name

        report = Report.search(
            [('model', '=', 'hr.payslip'), ('report_type', '=', 'qweb-pdf')],
            limit=1)
        if report:
            return report.report_name
        _logger.warning('No hr.payslip PDF report found; download disabled')
        return None