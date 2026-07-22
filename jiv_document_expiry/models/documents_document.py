# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

EXPIRING_SOON_DAYS = 30  # window used for "Expiring Soon" status/filter


class DocumentsDocument(models.Model):
    _inherit = 'documents.document'

    track_expiry = fields.Boolean(
        string="Track Expiry",
        help="Enable expiry tracking for this document.",
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        help="Date on which this document expires.",
    )
    expiry_status = fields.Selection(
        selection=[
            ('valid', 'Valid'),
            ('expiring', 'Expiring Soon'),
            ('expired', 'Expired'),
        ],
        string="Expiry Status",
        compute='_compute_expiry_status',
        search='_search_expiry_status',
    )

    @api.depends('track_expiry', 'expiry_date')
    def _compute_expiry_status(self):
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=EXPIRING_SOON_DAYS)
        for doc in self:
            if not doc.track_expiry or not doc.expiry_date:
                doc.expiry_status = False
            elif doc.expiry_date < today:
                doc.expiry_status = 'expired'
            elif doc.expiry_date <= soon:
                doc.expiry_status = 'expiring'
            else:
                doc.expiry_status = 'valid'

    def _search_expiry_status(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return [('id', 'in', [])]
        values = value if isinstance(value, (list, tuple)) else [value]
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=EXPIRING_SOON_DAYS)

        status_domains = {
            'expired': [
                ('track_expiry', '=', True),
                ('expiry_date', '!=', False),
                ('expiry_date', '<', today),
            ],
            'expiring': [
                ('track_expiry', '=', True),
                ('expiry_date', '>=', today),
                ('expiry_date', '<=', soon),
            ],
            'valid': [
                ('track_expiry', '=', True),
                ('expiry_date', '>', soon),
            ],
        }

        domains = [status_domains[v] for v in values if v in status_domains]
        if not domains:
            return [('id', 'in', [])]

        domain = domains[0]
        for extra in domains[1:]:
            domain = ['|'] + domain + extra
        if operator in ('!=', 'not in'):
            domain = ['!'] + domain
        return domain

    @api.onchange('track_expiry')
    def _onchange_track_expiry(self):
        if not self.track_expiry:
            self.expiry_date = False

    @api.model
    def _cron_document_expiry_reminder(self):
        """Daily cron: schedule a To-Do activity on documents expiring soon."""
        reminder_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'jiv_document_expiry.reminder_days', 7
            )
        )
        today = fields.Date.context_today(self)
        deadline = today + timedelta(days=reminder_days)

        documents = self.search([
            ('track_expiry', '=', True),
            ('expiry_date', '!=', False),
            ('expiry_date', '<=', deadline),
            ('expiry_date', '>=', today),
        ])
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False
        )
        for doc in documents:
            # Skip if a reminder activity already exists on this document
            existing = doc.activity_ids.filtered(
                lambda a: a.summary and a.summary.startswith('Document Expiry')
            )
            if existing:
                continue
            user = doc.owner_id or self.env.user
            try:
                doc.activity_schedule(
                    act_type_xmlid='mail.mail_activity_data_todo'
                    if activity_type else None,
                    date_deadline=doc.expiry_date,
                    summary=_("Document Expiry: %s", doc.name),
                    note=_(
                        "The document <b>%(name)s</b> expires on <b>%(date)s</b>. "
                        "Please review and renew it if required.",
                        name=doc.name,
                        date=doc.expiry_date.strftime('%d %b %Y'),
                    ),
                    user_id=user.id,
                )
            except Exception:
                _logger.exception(
                    "Failed to schedule expiry activity for document %s", doc.id
                )
        _logger.info(
            "Document expiry cron processed %s document(s).", len(documents)
        )
