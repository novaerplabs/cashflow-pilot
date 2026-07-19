/** @odoo-module **/

import { deserializeDate, formatDate } from "@web/core/l10n/dates";

// §15: dates are always shown via the user's locale format, never a
// hardcoded yyyy-mm-dd - every cockpit component formats server-supplied
// ISO date strings (period_start, period_end, low_point_week, ...)
// through this single helper rather than displaying them raw.
export function formatIsoDate(isoDateString) {
    if (!isoDateString) {
        return "";
    }
    return formatDate(deserializeDate(isoDateString));
}
