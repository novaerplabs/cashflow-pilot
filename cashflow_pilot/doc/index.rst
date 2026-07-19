==============
CashFlow Pilot
==============

A zero-configuration, rolling 13-week cash flow forecast for Odoo 19, built
automatically from data already in your database. CashFlow Pilot is strictly
read-only toward accounting: it never creates, modifies, or deletes journal
entries, invoices, bills, or reconciliations.

Key Features
============

* **Cash Cockpit** - today's position, a 13-week grid of inflows, outflows and
  closing balances, and the projected low point with the week it lands.
* **Drill-down** - click any cell to see the exact invoices, bills and planned
  items behind it; the total always reconciles to the cell.
* **10-minute onboarding** - a wizard confirms your bank and cash journals, sets
  your minimum-cash threshold, and helps you add recurring commitments.
* **Recurring & one-off items** - payroll, rent, GST/VAT, loan EMIs and more,
  projected across the horizon with effective-dated amount revisions.
* **Collections worklist** - Expected Receipts and Payments grouped by week, with
  at-risk flags and inline expected-date editing.
* **Data Readiness** - flags invoices without due dates, stale bank journals and
  missing exchange rates, with one-click links to fix them.
* **Threshold alerts** - exactly one activity and one email when a projected week
  dips below your threshold. No daily nagging.

Requirements
============

* Odoo 19.0 (Community or Enterprise)
* Depends on the standard ``account``, ``mail`` and ``web`` modules only.

Installation
============

1. Install **CashFlow Pilot** from the Apps menu.
2. Run the 10-minute onboarding wizard.
3. Open the Cash Cockpit and share it with your finance owner.

Data Sources
============

The forecast is computed from:

* Bank and cash journal balances.
* Posted customer invoices and vendor bills at their outstanding (residual) value.
* Recurring and one-off cash items you register in the app.

All computation happens inside your database. No external calls, no telemetry.

License
=======

This module is licensed under LGPL-3. See the ``LICENSE`` file for the full text.
