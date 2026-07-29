# jiv_portal_timesheet (Odoo 19)

Lets portal collaborators granted **Edit** access via *Share Project* log
their own time on shared tasks.

## Why it's needed

Portal "Edit" access only covers `project.task`. `account.analytic.line`
stays read-only for `base.group_portal`, and — more importantly —
`hr_timesheet._check_employee_id` rejects any line without an
`hr.employee`. Portal users have none. Both are handled here.

## Install order

1. Install the module.
2. **Settings > Project > Portal Timesheets** — decide whether to
   auto-create employees, set the back-dating window and max hours.
3. On the project: enable *Timesheets*, set visibility to
   *Invited portal users and all internal users*, then tick
   **Portal Timesheet Entry**.
4. Share the project with Edit access as you already do.

Collaborators reach the form at `/my/task/<id>/timesheets`.

## Odoo 19 version-safety notes

Two files are deliberately **not** wired in by default, because the
external IDs they inherit have moved between Odoo versions and a bad
XPath breaks the whole install:

| File | What it adds | How to enable |
|---|---|---|
| `views/portal_templates_inline.xml` | "Log Time" button on the portal task page | View ships `active="False"`. Settings > Technical > Views > *Portal: Task Log Time Button* > Active |
| `views/hr_timesheet_views_optional.xml` | Approval columns + filters on the backend timesheet list | Add to `data` in `__manifest__.py`, then upgrade |

Verify the IDs first, in the Odoo shell:

```python
for xid in [
    'project.portal_my_task',
    'hr_timesheet.hr_timesheet_line_tree',
    'hr_timesheet.hr_timesheet_line_search',
    'project.res_config_settings_view_form',
]:
    print(xid, bool(env.ref(xid, raise_if_not_found=False)))
```

Anything printing `False` needs its `inherit_id` adjusted before you
enable the corresponding view.

## Approval workflow

Portal entries are created as **To Approve** (`jiv_portal_state = draft`)
and frozen once reviewed. Approvers act from the backend timesheet list
via the *Approve / Refuse Portal Timesheets* actions.

**Invoicing:** if you bill from analytic lines, add
`('jiv_portal_state', '!=', 'draft')` to the invoicing domain, or
unreviewed collaborator hours will be billed.

## Guards in place

- Own lines only, and only while unapproved (`ir.rule` + `write`/`unlink` override)
- Portal users may only change `name`, `date`, `unit_amount`
- Back-dating window and max-hours-per-entry are configurable
- Future dates rejected
- `_document_check_access` runs before any `sudo()` in the controller
