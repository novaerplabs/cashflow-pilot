/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// FR-CFG-06: surfaces open readiness issues on the cockpit with a link
// through to the full Data Readiness Check list.
export class ReadinessStrip extends Component {
    static template = "cashflow_pilot.ReadinessStrip";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ issues: [] });
        onWillStart(async () => {
            this.state.issues = await this.orm.call("nova.readiness.issue", "get_cockpit_issues", []);
        });
    }

    async openReadiness() {
        await this.action.doAction("cashflow_pilot.nova_readiness_issue_action");
    }
}
