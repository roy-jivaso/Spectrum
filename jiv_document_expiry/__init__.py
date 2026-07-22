# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)

KANBAN_FIELDS_ARCH = """<data>
    <xpath expr="//templates" position="before">
        <field name="track_expiry"/>
        <field name="expiry_date"/>
        <field name="expiry_status"/>
    </xpath>
</data>"""


def post_init_hook(env):
    """Declare the expiry fields on every primary kanban view of
    documents.document so the OWL details panel (which reads the
    kanban/list record) has them loaded. The panel UI itself is added
    via a JS template extension in static/src.
    """
    View = env['ir.ui.view']
    IMD = env['ir.model.data']

    targets = View.search([
        ('model', '=', 'documents.document'),
        ('type', '=', 'kanban'),
        ('mode', '=', 'primary'),
    ])
    if not targets:
        _logger.warning(
            "jiv_document_expiry: no primary kanban views found for "
            "documents.document."
        )
        return

    for target in targets:
        xml_name = 'view_kanban_expiry_inherit_%s' % target.id
        if IMD.search_count([
            ('module', '=', 'jiv_document_expiry'),
            ('name', '=', xml_name),
        ]):
            continue
        try:
            view = View.create({
                'name': '%s.expiry.fields' % (target.name or 'documents.kanban'),
                'model': 'documents.document',
                'inherit_id': target.id,
                'mode': 'extension',
                'priority': 99,
                'arch_base': KANBAN_FIELDS_ARCH,
            })
        except Exception:
            _logger.exception(
                "jiv_document_expiry: could not inherit kanban view %s (%s)",
                target.id, target.name,
            )
            continue
        IMD.create({
            'module': 'jiv_document_expiry',
            'name': xml_name,
            'model': 'ir.ui.view',
            'res_id': view.id,
            'noupdate': True,
        })
        _logger.info(
            "jiv_document_expiry: declared expiry fields on kanban view %s (%s)",
            target.id, target.name,
        )
