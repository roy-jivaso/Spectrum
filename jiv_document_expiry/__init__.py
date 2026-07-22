# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)

EXPIRY_ARCH = """<data>
    <xpath expr="//form" position="inside">
        <group name="expiry_tracking" string="Expiry Tracking">
            <field name="track_expiry"/>
            <field name="expiry_date"
                   invisible="not track_expiry"
                   required="track_expiry"/>
            <field name="expiry_status"
                   invisible="not track_expiry"/>
        </group>
    </xpath>
</data>"""


def post_init_hook(env):
    """Attach the expiry group to every primary form view of
    documents.document, whatever their xml_ids are in this build.

    The Documents details panel in Odoo 19 is rendered from form
    view(s) whose xml_ids vary between builds (e.g. split info/tags
    views), so we resolve them at install time instead of hardcoding
    a ``ref``.
    """
    View = env['ir.ui.view']
    IMD = env['ir.model.data']

    targets = View.search([
        ('model', '=', 'documents.document'),
        ('type', '=', 'form'),
        ('mode', '=', 'primary'),
    ])
    if not targets:
        _logger.warning(
            "jiv_document_expiry: no primary form views found for "
            "documents.document; expiry fields will only be available "
            "in the list view."
        )
        return

    for target in targets:
        xml_name = 'view_form_expiry_inherit_%s' % target.id
        if IMD.search_count([
            ('module', '=', 'jiv_document_expiry'),
            ('name', '=', xml_name),
        ]):
            continue
        try:
            view = View.create({
                'name': '%s.expiry.inherit' % (target.name or 'documents.form'),
                'model': 'documents.document',
                'inherit_id': target.id,
                'mode': 'extension',
                'priority': 99,
                'arch_base': EXPIRY_ARCH,
            })
        except Exception:
            _logger.exception(
                "jiv_document_expiry: could not inherit form view %s (%s)",
                target.id, target.name,
            )
            continue
        # Register under this module so the view is removed on uninstall
        IMD.create({
            'module': 'jiv_document_expiry',
            'name': xml_name,
            'model': 'ir.ui.view',
            'res_id': view.id,
            'noupdate': True,
        })
        _logger.info(
            "jiv_document_expiry: added expiry group to form view %s (%s)",
            target.id, target.name,
        )
