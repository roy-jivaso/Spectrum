# jiv_portal_payslip (Odoo 19)

Employees view and download their own payslips from the portal.

## What it does

- "Payslips" card on My Account
- `/my/payslips` — own payslips, sortable by period / reference / status
- `/my/payslip/<id>` — detail with salary lines
- `/my/payslip/<id>/pdf` — PDF download

## Deliberately read-only

Portal users cannot create, write, or delete payslips. This is enforced
in three places, not one:

1. ACL grants read only
2. Record rules restrict to own records
3. `create`/`write`/`unlink` overrides raise for portal users

Belt and braces is appropriate here — a payroll leak is not a bug you
can quietly fix afterwards.

## Only confirmed payslips are visible

Default visible states are `done` and `paid`. Draft and `verify` slips
are hidden because the figures still move while payroll is working, and
an employee who sees a number that later changes will reasonably treat
the first one as a promise.

To change it, set `jiv_portal_payslip.visible_states`, e.g.
`['verify', 'done', 'paid']` — **and update the matching record rules in
`security/portal_payslip_rules.xml`**. The parameter only affects the
controller; the rule is the actual boundary and it hardcodes
`['done', 'paid']`.

## Before going live

- Confirm the PDF report resolves. The report xml id differs across
  payroll versions and localisations, so the controller tries several
  names and falls back to searching `ir.actions.report`. If none is
  found the download button still renders but redirects back — check
  once with a real payslip.
- Decide whether payslip *lines* should be visible at all. The detail
  page lists them (filtered by `appears_on_payslip` where that field
  exists). If your rules include internal-only lines, hide the table.
- `hr.payslip` now inherits `portal.mixin`, which adds an `access_token`
  column. Uninstalling will not remove it.
