{
    'name': 'Portal Attendance',
    'version': '19.0.1.0.0',
    'summary': 'Let portal users check in and out from My Account',
    'description': """
Portal Attendance
=================

Adds an "Attendances" card to the portal My Account page and a portal
page where the logged-in user can:

* Check In / Check Out with a single button (one open record at a time)
* See their own attendance history with duration
* Sort by Check In / Check Out / Duration
* Filter by Today, This week, This month, This quarter, This year,
  Last week, Last month, Last year
* Search their records

Notes
-----
* Records are stored on hr.attendance and flagged with
  jiv_from_portal so they can be excluded from HR reporting.
* hr.attendance requires an hr.employee; one can be auto-provisioned
  (see Settings > Technical > System Parameters).
""",
    'author': 'Zyvi Technologies',
    'website': 'https://www.zyvitech.com',
    'category': 'Human Resources/Attendances',
    'license': 'LGPL-3',
    'depends': ['hr_attendance', 'portal'],
    'data': [
        'security/portal_attendance_groups.xml',
        'security/ir.model.access.csv',
        'security/portal_attendance_rules.xml',
        'data/portal_attendance_data.xml',
        'views/res_config_settings_views.xml',
        'views/hr_attendance_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'jiv_portal_attendance/static/src/scss/portal_attendance.scss',
        ],
    },
    'installable': True,
    'application': False,
}
