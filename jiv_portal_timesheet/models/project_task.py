from odoo import api, models, tools


class ProjectTask(models.Model):
    _inherit = 'project.task'

    @api.model
    @tools.ormcache(cache='stable')
    def _portal_accessible_fields(self):
        """Add 'timesheet_ids' to the fields portal users may write.

        Odoo restricts Project Sharing writes to the field set in
        TASK_PORTAL_WRITABLE_FIELDS; 'timesheet_ids' is not in it, so the
        embedded timesheet list is rejected with:

            Access Denied by ACLs for operation: write,
            model: project.task, field: timesheet_ids

        Overriding the accessor rather than reassigning the class
        attribute avoids depending on the defining class's import path,
        which has moved between versions.

        SCOPE WARNING
        =============
        This set is global to project.task and is ormcached, so it cannot
        be varied per project or per company. Enabling this module opens
        timesheet writes for ANY portal user with Project Sharing write
        access on ANY project in this database - not only projects with
        jiv_allow_portal_timesheet ticked. That flag gates the view, not
        this whitelist.

        What still constrains the data:
          - ir.rule on account.analytic.line: own lines only, draft only
          - create() override: stamps portal origin, forces approval state
          - write()/unlink() overrides: field-level restrictions

        Note the ormcache: changes here only take effect after a registry
        reload (module upgrade or service restart).
        """
        readable, writable = super()._portal_accessible_fields()
        writable = writable | {'timesheet_ids'}
        return readable | writable, writable
