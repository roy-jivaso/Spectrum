# -*- coding: utf-8 -*-
{
    'name': 'Documents Expiry Tracking',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Track expiry dates on documents with reminders',
    'description': """
Documents Expiry Tracking
=========================
Adds a "Track Expiry" checkbox and "Expiry Date" field on documents.

Features:
- Track Expiry checkbox + Expiry Date on the document details panel
- Both fields available as optional columns in the Documents list view
- Expired / Expiring Soon row highlighting in list view
- Search filters: Track Expiry, Expired, Expiring in 30 Days
- Daily cron that schedules a reminder activity on the document owner
  before the expiry date (configurable lead days via system parameter
  `jiv_document_expiry.reminder_days`, default 7)
""",
    'author': 'Zyvi Technologies',
    'website': 'https://zyvitech.com',
    'license': 'LGPL-3',
    'depends': ['documents'],
    'data': [
        'views/documents_document_views.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': False,
}
