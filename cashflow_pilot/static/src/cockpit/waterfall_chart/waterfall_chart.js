/** @odoo-module **/

import { Component, useRef, onWillStart, onMounted, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { formatIsoDate } from "../date_utils";

// FR-VIEW-07: per-period net-movement waterfall, approximated with Chart.js
// floating bars (opening -> closing per period, colored by net sign).
export class WaterfallChart extends Component {
    static template = "cashflow_pilot.WaterfallChart";
    static props = {
        periods: { type: Array, optional: true },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = null;
        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
        });
        onMounted(() => this.renderChart());
        onWillUpdateProps((nextProps) => this.renderChart(nextProps.periods));
        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }

    renderChart(periods) {
        periods = periods || this.props.periods || [];
        if (!this.canvasRef.el || !periods.length) {
            return;
        }
        if (this.chart) {
            this.chart.destroy();
        }
        this.chart = new window.Chart(this.canvasRef.el, {
            type: "bar",
            data: {
                labels: periods.map((p) => formatIsoDate(p.period_start)),
                datasets: [
                    {
                        label: _t("Net Movement"),
                        data: periods.map((p) => [p.opening, p.closing]),
                        backgroundColor: periods.map((p) => (p.net >= 0 ? "#2ca02c" : "#d62728")),
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
            },
        });
    }
}
