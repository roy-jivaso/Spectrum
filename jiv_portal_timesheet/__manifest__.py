{
    'name': 'Portal Timesheet Entry',
    'version': '19.0.1.0.0',
    'summary': 'Allow portal collaborators to log timesheets on shared project tasks',
    'description': """
Portal Timesheet Entry
======================

Lets portal users who have been granted Edit access via Share Project
record their own timesheet lines directly from the portal task page.

Key points
----------
* Portal users must be linked to an hr.employee record. The module can
  auto-provision one (see Settings > Project > Portal Timesheets).
* Portal-created lines are flagged and stay unvalidated until an internal
  user approves them, so they can be excluded from invoicing.
* Users may only edit/delete their own lines, and only while unvalidated.
""",

    'category': 'Services/Timesheets',
    'license': 'LGPL-3',
    'depends': ['hr_timesheet', 'project', 'portal'],
    'data': [
        'security/ir.model.access.csv',
        'security/portal_timesheet_rules.xml',
        'data/portal_timesheet_data.xml',
        'views/hr_timesheet_views.xml',
        'views/portal_timesheet_page.xml',
        'views/portal_templates_inline.xml',
        'views/project_sharing_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'jiv_portal_timesheet/static/src/scss/portal_timesheet.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
