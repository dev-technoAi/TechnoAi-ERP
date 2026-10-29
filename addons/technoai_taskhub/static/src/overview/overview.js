import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { playAlertSound } from "../alert_sounds";

const { DateTime } = luxon;
const REFRESH_MS = 30000;

export class TaskhubOverview extends Component {
    static template = "technoai_taskhub.Overview";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, tab: "todo", show: "everyone", search: "" });
        // the sound plays once each time a new task reaches the alert banner
        this.alertedTaskId = null;

        onWillStart(() => this.load());
        const timer = setInterval(() => this.load(), REFRESH_MS);
        onWillUnmount(() => clearInterval(timer));
    }

    async load() {
        const data = await this.orm.call("taskhub.task", "get_overview", [], { show: this.state.show });
        this.state.data = data;
        const alertId = data.alert && data.alert.id;
        if (alertId && alertId !== this.alertedTaskId) {
            playAlertSound(data.sound, data.volume);
        }
        this.alertedTaskId = alertId || null;
    }

    get greeting() {
        const hour = DateTime.local().hour;
        const part = hour < 12 ? _t("Good morning") : hour < 17 ? _t("Good afternoon") : _t("Good evening");
        return `${part}, ${this.state.data.user_name}`;
    }

    get today() {
        return DateTime.local().toFormat("cccc, LLL d");
    }

    get tabs() {
        const tabs = this.state.data.tabs;
        return [
            { key: "todo", label: _t("To do"), count: tabs.todo.length },
            { key: "today", label: _t("Today"), count: tabs.today.length },
            { key: "overdue", label: _t("Overdue"), count: tabs.overdue.length },
            { key: "done", label: _t("Done"), count: tabs.done.length },
        ];
    }

    get tasks() {
        const query = this.state.search.trim().toLowerCase();
        const tasks = this.state.data.tabs[this.state.tab];
        if (!query) {
            return tasks;
        }
        return tasks.filter((task) =>
            [task.name, task.department, task.user, task.linked].some((value) => (value || "").toLowerCase().includes(query))
        );
    }

    dueLabel(task) {
        if (!task.deadline) {
            return "";
        }
        const due = deserializeDateTime(task.deadline);
        const now = DateTime.local();
        const time = due.toFormat("HH:mm");
        let day;
        if (due.hasSame(now, "day")) {
            day = _t("Today %s", time);
        } else if (due.hasSame(now.plus({ days: 1 }), "day")) {
            day = _t("Tomorrow %s", time);
        } else if (due.hasSame(now.minus({ days: 1 }), "day")) {
            day = _t("Yesterday %s", time);
        } else {
            day = due.toFormat("d LLL HH:mm");
        }
        return task.overdue ? _t("Overdue · %s", day) : day;
    }

    alertTime(task) {
        return task.deadline ? deserializeDateTime(task.deadline).toFormat("hh:mm a") : "";
    }

    async setShow(ev) {
        this.state.show = ev.target.value;
        await this.load();
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
    }

    async snooze(minutes) {
        await this.orm.call("taskhub.task", "action_snooze_alert", [[this.state.data.alert.id], minutes]);
        this.notification.add(_t("Snoozed for %s minutes", minutes), { type: "info" });
        await this.load();
    }

    async dismiss() {
        await this.orm.call("taskhub.task", "action_dismiss_alert", [[this.state.data.alert.id]]);
        await this.load();
    }

    async toggleDone(task) {
        const method = task.state === "done" ? "action_reopen" : "action_mark_done";
        await this.orm.call("taskhub.task", method, [[task.id]]);
        await this.load();
    }

    openTask(task) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "taskhub.task",
            res_id: task.id,
            views: [[false, "form"]],
        });
    }

    newTask() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "taskhub.task",
            views: [[false, "form"]],
            target: "current",
        });
    }

    useTemplate() {
        this.action.doAction("technoai_taskhub.taskhub_template_action");
    }

    openViews(viewType) {
        this.action.doAction("technoai_taskhub.taskhub_task_action", { viewType });
    }
}

registry.category("actions").add("technoai_taskhub.overview", TaskhubOverview);
