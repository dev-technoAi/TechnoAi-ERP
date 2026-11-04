import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STATUS_COLORS = {
    processing: "#c9d3d8",
    ready_to_ship: "#7cc4d6",
    in_transit: "#f0b85a",
    in_inventory: "#a08ae0",
    ready_for_delivery: "#5aa9e6",
    delivered: "#0FAD98",
};

/** Order Tracking at a glance: figures, items by status and the open orders. */
export class TrackingDashboard extends Component {
    static template = "technoai_tracking.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null });
        this.colors = STATUS_COLORS;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("technoai.tracking.order", "get_dashboard_data", []);
    }

    get totalItems() {
        return this.state.data.statuses.reduce((sum, status) => sum + status.count, 0) || 1;
    }

    openOrder(id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "technoai.tracking.order", res_id: id, views: [[false, "form"]] });
    }

    openList(filter) {
        this.action.doAction("technoai_tracking.tracking_order_action", {
            additionalContext: filter ? { [`search_default_${filter}`]: 1 } : {},
        });
    }

    openLate() {
        this.action.doAction("technoai_tracking.tracking_line_late_action");
    }
}

registry.category("actions").add("technoai_tracking_dashboard", TrackingDashboard);
