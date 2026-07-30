# jiv_portal_attendance (Odoo 19)

Portal users check in / check out from **My Account > Attendances**.

## What it does

- "Attendances" card on the portal home, with a record count
- `/my/attendances` — own records with Check In / Check Out, duration
- Sort by Check In / Check Out / Duration
- Filter: All, Today, This week/month/quarter/year, Last week/month/year
- Notification banner after check in / out
- One open record at a time; re-checking-in while open is refused

## Setup

**Settings > Portal Attendance** (own section in the Settings app):

- *Restrict to Selected Users* - limit check-in to the "Portal
  Attendance" group. Off by default, meaning every portal user on the
  database can check in, including customers on unrelated projects.
- *Auto-create Employee* + *Department*
- *Check In Automatically on Login*

These write the system parameters below, which can also be edited
directly under Settings > Technical > System Parameters:

| Key | Default | Meaning |
|---|---|---|
| `auto_create_employee` | `True` | Provision an `hr.employee` on first check-in |
| `employee_department_id` | *(unset)* | Department for auto-created employees |
| `checkin_on_login` | *(empty = off)* | See below |
| `restrict_group` | *(empty = off)* | Require the Portal Attendance group |

**Note:** `get_param` returns strings, so `'False'` is truthy. To disable
a flag set the value to an **empty string**, not `False`.

## checkin_on_login is off by default — deliberately

The reference behaviour was to create a checked-in attendance whenever a
portal user logs in without one. That records attendance the user never
initiated: a late-night login to read a message becomes a shift, and it
feeds `worked_hours` and overtime. The parameter exists but ships empty.
Enable it only if the client explicitly wants login treated as arrival,
and expect to explain the resulting hours.

*(The hook itself is not implemented — enabling the parameter alone does
nothing. Ask if you want it wired up.)*

## Data hygiene

Records made from the portal carry `jiv_from_portal = True`. The
attendance search view gains **From Portal** / **Internal Only** filters.

**This matters:** portal users here are external collaborators with stub
employee records. Their check-ins land in the same `hr.attendance` table
as staff, so they appear in attendance reporting, `worked_hours`, and
overtime computation unless excluded. If this instance runs payroll off
attendance, filter on `jiv_from_portal = False` in those flows before
going live.

## Guards

- Record rule: own records only (`employee_id.user_id = user.id`)
- Portal users may only write `check_out`; everything else refused
- Portal users cannot delete records at all
- `jiv_skip_portal_field_check` context lets Odoo's own post-checkout
  recompute (worked_hours, overtime) through without tripping the
  whitelist — same pattern as jiv_portal_timesheet

## Timezone

Filter windows are computed in the user's timezone and converted to UTC,
because `check_in` is stored naive-UTC. Filtering on server day
boundaries would misfile evening records for anyone outside UTC.
