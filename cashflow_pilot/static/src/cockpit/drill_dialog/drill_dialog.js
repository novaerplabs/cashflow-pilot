/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { formatIsoDate } from "../date_utils";

// FR-VIEW-04/05, AC-07: document list for a cell, total reconciles to the
// cell value; inline expected-date edit writes via nova.move.info and
// triggers the targeted recompute (§16), never touching accounting data.
export class DrillDialog extends Component {
    static template = "cashflow_pilot.DrillDialog";
    static components = { Dialog };
    static props = {
        periodStart: String,
        periodLabel: { type: String, optional: true },
        granularity: String,
        categoryId: { type: [Number, Boolean], optional: true },
        direction: { type: [String, Boolean], optional: true },
        onEdited: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            lines: [],
            currencyId: false,
            loading: true,
            editingId: false,
            editDate: "",
        });
        onWillStart(async () => {
            await this.loadLines();
        });
    }

    async loadLines() {
        this.state.loading = true;
        const result = await this.orm.call("nova.period.report", "get_cockpit_drill", [
            this.props.periodStart,
            this.props.granularity,
            this.props.categoryId || false,
            this.props.direction || false,
        ]);
        this.state.lines = result.lines;
        this.state.currencyId = result.currency_id;
        this.state.loading = false;
    }

    get total() {
        return this.state.lines.reduce((sum, line) => sum + line.amount, 0);
    }

    formatAmount(amount) {
        return this.state.currencyId ? formatCurrency(amount, this.state.currencyId) : amount;
    }

    formatDate(isoDateString) {
        return formatIsoDate(isoDateString);
    }

    startEdit(line) {
        this.state.editingId = line.id;
        this.state.editDate = line.expected_date;
    }

    cancelEdit() {
        this.state.editingId = false;
    }

    async confirmEdit(line) {
        await this.orm.call("nova.move.info", "set_expected_date", [
            [line.move_info_id],
            this.state.editDate,
        ]);
        this.state.editingId = false;
        await this.loadLines();
        if (this.props.onEdited) {
            this.props.onEdited();
        }
    }
}
