/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { KpiCards } from "./kpi_cards/kpi_cards";
import { ForecastGrid } from "./forecast_grid/forecast_grid";
import { TrendChart } from "./trend_chart/trend_chart";
import { WaterfallChart } from "./waterfall_chart/waterfall_chart";
import { AlertStrip } from "./alert_strip/alert_strip";
import { ReadinessStrip } from "./readiness_strip/readiness_strip";

// Root cockpit client action (README §10.2, D-01). Loads progressively:
// KPIs first, then the grid, then the charts (§16 performance).
export class NovaCockpit extends Component {
    static template = "cashflow_pilot.NovaCockpit";
    static components = { KpiCards, ForecastGrid, TrendChart, WaterfallChart, AlertStrip, ReadinessStrip };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            granularity: "week",
            kpis: null,
            grid: null,
            loadingKpis: true,
            loadingGrid: true,
            refreshing: false,
        });
        onWillStart(async () => {
            // UC-01: the wizard launches on first open (Manager role only,
            // since only Managers can access it - see nova_group_manager
            // ACL) and never auto-forces again once onboarding is done.
            const status = await this.orm.call("res.company", "get_onboarding_status", []);
            if (!status.onboarding_done) {
                const isManager = await user.hasGroup("cashflow_pilot.nova_group_manager");
                if (isManager) {
                    await this.action.doAction("cashflow_pilot.nova_onboarding_wizard_action");
                    return;
                }
            }
            await this.loadKpis();
            await this.loadGrid();
        });
    }

    async loadKpis() {
        this.state.loadingKpis = true;
        this.state.kpis = await this.orm.call("nova.period.report", "get_cockpit_kpis", []);
        this.state.loadingKpis = false;
    }

    async loadGrid() {
        this.state.loadingGrid = true;
        this.state.grid = await this.orm.call(
            "nova.period.report", "get_cockpit_grid", [this.state.granularity]
        );
        this.state.loadingGrid = false;
    }

    async setGranularity(granularity) {
        if (this.state.granularity === granularity) {
            return;
        }
        this.state.granularity = granularity;
        await this.loadGrid();
    }

    async onRefresh() {
        this.state.refreshing = true;
        try {
            await this.orm.call("res.company", "action_refresh_forecast_current_company", []);
            await this.loadKpis();
            await this.loadGrid();
        } finally {
            this.state.refreshing = false;
        }
    }

    async onCellEdited() {
        // A drill-dialog inline edit already ran the targeted recompute
        // server-side; just refresh what the cockpit displays.
        await this.loadKpis();
        await this.loadGrid();
    }

    onExportXlsx() {
        // R-01: plain HTTP download, current session's company/granularity.
        window.open(`/cashflow_pilot/export/forecast_xlsx?granularity=${this.state.granularity}`);
    }

    onExportPdf() {
        window.open(`/cashflow_pilot/export/forecast_pdf?granularity=${this.state.granularity}`);
    }
}

registry.category("actions").add("nova_cockpit", NovaCockpit);
