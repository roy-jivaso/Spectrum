from odoo import api, models, tools
from odoo.exceptions import AccessError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    def action_jiv_send_email(self):
        self.ensure_one()
        ctx = {
            'default_model': 'project.task',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_partner_ids': self.partner_id.ids,
            'mark_task_as_sent': True,
            'force_email': True,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Email'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def write(self, vals):
        if self.env.user._is_portal() and not self.env.context.get(
                'jiv_skip_portal_field_check'
        ):
            foreign = self.sudo().filtered(
                lambda t: t.create_uid.id != self.env.uid
            )
            if foreign:
                raise AccessError(
                    "You can only edit tasks you created yourself."
                )
        if (
                'project_id' in vals
                and self.env.user._is_portal()
                and not self.env.context.get('jiv_skip_portal_field_check')
        ):
            self._jiv_check_portal_project(vals['project_id'])
        return super().write(vals)

    @api.model
    @tools.ormcache(cache='stable')
    def _portal_accessible_fields(self):
        """Add 'timesheet_ids' to the fields portal users may write, plus
        the fields required to CREATE a task.

        Odoo restricts Project Sharing writes to the field set in
        TASK_PORTAL_WRITABLE_FIELDS; 'timesheet_ids' is not in it, so the
        embedded timesheet list is rejected with:

            Access Denied by ACLs for operation: write,
            model: project.task, field: timesheet_ids

        'project_id' and 'parent_id' are added for the same reason on
        create: every key in the vals dict is checked against this set,
        and a create from the sharing view always carries project_id.

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

        Adding 'project_id' widens this further: a portal user could
        re-parent an existing task into another project they collaborate
        on. create() and write() below re-validate the target project
        against edit-level collaboration.

        What still constrains the data:
          - ir.rule on account.analytic.line: own lines only, draft only
          - ir.rule on project.task (perm_create): collaborator projects
          - create() override: stamps portal origin, forces approval state
          - write()/unlink() overrides: field-level restrictions

        Note the ormcache: changes here only take effect after a registry
        reload (module upgrade or service restart).
        """
        readable, writable = super()._portal_accessible_fields()
        writable = writable | {
            'timesheet_ids',
            'project_id',
            'parent_id',
            'x_studio_assignees',
        }
        return readable | writable, writable

    def _jiv_check_portal_project(self, project_id):
        """Raise unless the current portal user is an edit collaborator.

        project.collaborator has no access_mode field in Odoo 19; the
        read-only flag is limited_access (True = read only).
        """
        if not project_id:
            raise AccessError(
                "A project must be selected when creating a task."
            )
        collab = self.env['project.collaborator'].sudo().search([
            ('project_id', '=', project_id),
            ('partner_id', '=', self.env.user.partner_id.id),
        ], limit=1)
        if not collab or collab.limited_access:
            raise AccessError(
                "You do not have edit access to this project."
            )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._is_portal() and not self.env.context.get(
                'jiv_skip_portal_field_check'
        ):
            # Project Sharing passes the project via context on quick
            # create; only the form carries it in vals.
            ctx_project = self.env.context.get('default_project_id')
            for vals in vals_list:
                project_id = vals.get('project_id') or ctx_project
                self._jiv_check_portal_project(project_id)
                if not vals.get('project_id'):
                    vals['project_id'] = project_id
        return super().create(vals_list)

    def write(self, vals):
        if (
            'project_id' in vals
            and self.env.user._is_portal()
            and not self.env.context.get('jiv_skip_portal_field_check')
        ):
            self._jiv_check_portal_project(vals['project_id'])
        return super().write(vals)