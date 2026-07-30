{
    'name': 'Spectrum Client Intake Form',
    'version': '19.0.1.0.0',
    'summary': 'Send intake form link to prospects; capture submissions into CRM leads',
    'category': 'CRM',

    'depends': ['crm', 'website', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'views/intake_form_template.xml',
        'views/crm_lead_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'jiv_spectrum_intake/static/src/js/send_intake_dialog.js',
            'jiv_spectrum_intake/static/src/css/intake.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
