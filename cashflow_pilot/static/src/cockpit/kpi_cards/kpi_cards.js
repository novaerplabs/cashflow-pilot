/** @odoo-module **/

import { Component } from "@odoo/owl";
import { formatCurrency } from "@web/core/currency";
import { formatIsoDate } from "../date_utils";
import { _t } from "@web/core/l10n/translation";

// D-01 headline cards: cash today, low point (value+week), runway, net 4-week flow.
export class KpiCards extends Component {
    static template = "cashflow_pilot.KpiCards";
    static props = {
        kpis: { type: Object, optional: true },
        loading: { type: Boolean, optional: true },
    };

    formatAmount(amount) {
        const currencyId = this.props.kpis && this.props.kpis.currency_id;
        return currencyId ? formatCurrency(amount, currencyId) : amount;
    }

    formatDate(isoDateString) {
        return formatIsoDate(isoDateString);
    }

    get runwayLabel() {
        const kpis = this.props.kpis;
        if (!kpis || kpis.runway_weeks === false || kpis.runway_weeks === undefined) {
            return _t("No breach in horizon");
        }
        return _t("%s week(s)", kpis.runway_weeks);
    }
}
