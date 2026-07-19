/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { formatIsoDate } from "../date_utils";
import { DrillDialog } from "../drill_dialog/drill_dialog";

// FR-VIEW-01/02/03/04: rows opening/in-categories/out-categories/net/closing,
// columns = periods, breach cells highlighted, every cell drills down (AC-07).
export class ForecastGrid extends Component {
    static template = "cashflow_pilot.ForecastGrid";
    static props = {
        grid: { type: Object, optional: true },
        granularity: { type: String },
        loading: { type: Boolean, optional: true },
        onCellEdited: { type: Function, optional: true },
    };

    setup() {
        this.dialog = useService("dialog");
    }

    get periods() {
        return (this.props.grid && this.props.grid.periods) || [];
    }

    get inCategories() {
        return ((this.props.grid && this.props.grid.categories) || []).filter(
            (c) => c.direction === "in"
        );
    }

    get outCategories() {
        return ((this.props.grid && this.props.grid.categories) || []).filter(
            (c) => c.direction === "out"
        );
    }

    amountForCategory(category, period) {
        return category.amounts[period.period_start] || 0;
    }

    formatAmount(amount) {
        const currencyId = this.props.grid && this.props.grid.currency_id;
        return currencyId ? formatCurrency(amount, currencyId) : amount;
    }

    formatPeriodHeader(period) {
        return formatIsoDate(period.period_start);
    }

    onCellClick(period, category, direction) {
        this.dialog.add(DrillDialog, {
            periodStart: period.period_start,
            periodLabel: `${formatIsoDate(period.period_start)} - ${formatIsoDate(period.period_end)}`,
            granularity: this.props.granularity,
            categoryId: category ? category.category_id : false,
            direction: direction || false,
            onEdited: () => this.props.onCellEdited && this.props.onCellEdited(),
        });
    }
}
