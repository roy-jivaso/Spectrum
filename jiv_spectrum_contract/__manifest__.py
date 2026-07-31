{
    'name': 'Spectrum Client Service Agreement',
    'version': '19.0.1.0.0',
    'summary': 'Generate, send, and capture signed Client Service Agreements from CRM opportunities',
    'category': 'CRM',
    'author': 'Zyvi Technologies',
    'depends': ['crm', 'sign', 'mail', 'website', 'jiv_spectrum_intake'],
    'data': [
        'security/ir.model.access.csv',
        'data/report_paperformat.xml',
        'report/contract_report.xml',
        'views/wizard_generate_contract.xml',
        'views/crm_lead_views.xml',
        'views/sign_portal_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'jiv_spectrum_contract/static/src/css/contract.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
