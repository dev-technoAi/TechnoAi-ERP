import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class TaskhubReports extends Component {
    static template = "technoai_taskhub.Reports";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ days: 30, data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("taskhub.report", "get_report", [], { days: this.state.days });
    }

    async setDays(days) {
        this.state.days = days;
        await this.load();
    }

    money(value) {
        const { symbol, position } = this.state.data.currency;
        const amount = Math.round(value || 0).toLocaleString();
        return position === "before" ? `${symbol} ${amount}` : `${amount} ${symbol}`;
    }

    get kpis() {
        const k = this.state.data.kpis;
        const change = k.won_change === null ? _t("no earlier wins") : `${k.won_change >= 0 ? "↗" : "↘"} ${Math.abs(k.won_change)}% ${_t("vs previous")}`;
        return [
            { label: _t("Won revenue"), value: this.money(k.won_revenue), note: change, open: "won" },
            { label: _t("Inbound RFQs"), value: k.inbound_rfqs, note: _t("%s this week", k.inbound_week), open: "rfqs" },
            { label: _t("Tasks completed"), value: k.tasks_done, note: k.on_time_percent === null ? "" : `${k.on_time_percent}% ${_t("on time")}`, open: "tasks" },
            { label: _t("Avg deal size"), value: this.money(k.avg_deal), note: k.win_rate === null ? "" : `${_t("win rate")} ${k.win_rate}%`, open: "won" },
            { label: _t("Active pipeline"), value: this.money(k.active_pipeline), note: _t("%s open RFQs", k.open_rfqs), open: "rfqs" },
            { label: _t("Gross margin"), value: `${k.gross_margin}%`, note: _t("on quoted prices"), open: "quotes" },
        ];
    }

    get bars() {
        const rows = this.state.data.revenue;
        const max = Math.max(1, ...rows.map((r) => Math.max(r.value, r.previous)));
        const step = Math.max(1, Math.ceil(rows.length / 6));
        return rows.map((row, i) => ({
            ...row,
            height: (row.value / max) * 100,
            prevHeight: (row.previous / max) * 100,
            showLabel: i % step === 0 || i === rows.length - 1,
            title: `${row.label}: ${this.money(row.value)} (${_t("previous")}: ${this.money(row.previous)})`,
        }));
    }

    get workload() {
        const rows = this.state.data.workload;
        const max = Math.max(1, ...rows.map((r) => r.open_tasks));
        return rows.map((row) => ({ ...row, width: (row.open_tasks / max) * 100, initials: row.name.split(" ").map((w) => w[0]).join("").slice(0, 2) }));
    }

    open(target) {
        const actions = {
            won: ["technoai_taskhub.taskhub_rfq_action", { additionalContext: { search_default_state_won: 1, search_default_open: 0 } }],
            rfqs: ["technoai_taskhub.taskhub_rfq_action", {}],
            tasks: ["technoai_taskhub.taskhub_task_action", { additionalContext: { search_default_done: 1, search_default_open: 0 } }],
            quotes: ["technoai_taskhub.taskhub_quotation_action", {}],
        };
        const [action, options] = actions[target];
        this.action.doAction(action, options);
    }

    openUserTasks(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: row.name,
            res_model: "taskhub.task",
            views: [[false, "list"], [false, "form"]],
            domain: [["user_id", "=", row.user_id], ["state", "!=", "done"]],
        });
    }

    exportCsv() {
        const d = this.state.data;
        const lines = [[_t("Metric"), _t("Value")]];
        for (const kpi of this.kpis) {
            lines.push([kpi.label, kpi.value]);
        }
        lines.push([], [_t("Day"), _t("Won revenue"), _t("Previous period")]);
        for (const row of d.revenue) {
            lines.push([row.label, row.value, row.previous]);
        }
        lines.push([], [_t("Team member"), _t("Department"), _t("Open tasks")]);
        for (const row of d.workload) {
            lines.push([row.name, row.department, row.open_tasks]);
        }
        const csv = lines.map((cols) => cols.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
        const link = Object.assign(document.createElement("a"), { href: url, download: `task-hub-report-${d.days}-days.csv` });
        link.click();
        URL.revokeObjectURL(url);
    }
}

registry.category("actions").add("technoai_taskhub.reports", TaskhubReports);
