{
    'name': 'Portal Payslips',
    'version': '19.0.1.0.0',
    'summary': 'Let employees view and download their own payslips from the portal',
    'description': """
Portal Payslips
===============

Adds a "Payslips" card to the portal My Account page where an employee
can see their own payslips and download the PDF.

Deliberately read-only. Portal users cannot create, edit, delete, or
recompute anything - payslips are produced in the backend by payroll
staff and this module only exposes them.

Only *confirmed* payslips are visible by default (state done/paid).
Draft and computed-but-unconfirmed slips are hidden, because figures
still change at that stage and showing them to employees causes
avoidable disputes. Configurable if you disagree - see the README.
""",
    'author': 'Zyvi Technologies',
    'website': 'https://www.zyvitech.com',
    'category': 'Human Resources/Payroll',
    'license': 'LGPL-3',
    'depends': ['hr_payroll', 'portal'],
    'data': [
        'security/ir.model.access.csv',
        'security/portal_payslip_rules.xml',
        'data/portal_payslip_data.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
}
