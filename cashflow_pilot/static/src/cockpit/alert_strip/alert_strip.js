/** @odoo-module **/

import { Component } from "@odoo/owl";

// BR-11: shown only while breached; recovery is silent (no banner) by design.
export class AlertStrip extends Component {
    static template = "cashflow_pilot.AlertStrip";
    static props = {
        breachState: { type: String, optional: true },
    };
}
