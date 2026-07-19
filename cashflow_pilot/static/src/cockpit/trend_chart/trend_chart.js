/** @odoo-module **/

import { Component, useRef, onWillStart, onMounted, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { formatIsoDate } from "../date_utils";

// FR-VIEW-07: closing-balance trend line with a threshold rule-line overlay.
// Uses Odoo's bundled Chart.js (HR-6: no new chart dependency).
export class TrendChart extends Component {
    static template = "cashflow_pilot.TrendChart";
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
            type: "line",
            data: {
                labels: periods.map((p) => formatIsoDate(p.period_start)),
                datasets: [
                    {
                        label: _t("Closing Balance"),
                        data: periods.map((p) => p.closing),
                        borderColor: "#1f77b4",
                        fill: false,
                    },
                    {
                        label: _t("Threshold"),
                        data: periods.map((p) => p.threshold),
                        borderColor: "#d62728",
                        borderDash: [6, 4],
                        pointRadius: 0,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
            },
        });
    }
}
