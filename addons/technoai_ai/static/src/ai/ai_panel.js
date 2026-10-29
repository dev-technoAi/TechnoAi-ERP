import { Component, markup, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { escape } from "@web/core/utils/strings";

const COLORS = ["#1F869E", "#0FAD98", "#B7791F", "#8E4F87", "#C2453B", "#3A5A6A", "#E8702A", "#17708A", "#5B6B75", "#1D8560"];

function inline(text) {
    return text
        .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/** Small, safe markdown: everything is escaped first, then bold, code, lists, headings and tables. */
export function formatText(text) {
    const lines = escape(text || "").split("\n");
    const out = [];
    let list = null;
    let table = null;
    const flush = () => {
        if (list) {
            out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`);
            list = null;
        }
        if (table) {
            const rows = table.filter((row) => !/^\|?\s*:?-{2,}/.test(row));
            const cells = (row) => row.replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));
            const [head, ...body] = rows;
            out.push(
                `<table class="table table-sm o_tai_ai_table"><thead><tr>${cells(head).map((c) => `<th>${c}</th>`).join("")}</tr></thead>` +
                    `<tbody>${body.map((r) => `<tr>${cells(r).map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`
            );
            table = null;
        }
    };
    for (const raw of lines) {
        const line = raw.trimEnd();
        const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
        const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
        if (line.trim().startsWith("|")) {
            if (list) {
                flush();
            }
            table = table || [];
            table.push(line.trim());
        } else if (bullet || numbered) {
            const tag = bullet ? "ul" : "ol";
            if (table || (list && list.tag !== tag)) {
                flush();
            }
            list = list || { tag, items: [] };
            list.items.push((bullet || numbered)[1]);
        } else {
            flush();
            const heading = line.match(/^#{1,4}\s+(.*)$/);
            if (heading) {
                out.push(`<div class="fw-bold mt-1">${inline(heading[1])}</div>`);
            } else if (line.trim()) {
                out.push(`<p>${inline(line)}</p>`);
            }
        }
    }
    flush();
    return markup(out.join(""));
}

export class AiChart extends Component {
    static template = "technoai_ai.AiChart";
    static props = { item: Object };

    setup() {
        this.canvas = useRef("canvas");
        onWillStart(() => loadBundle("web.chartjs_lib"));
        onMounted(() => this.renderChart());
        onWillUnmount(() => this.chart?.destroy());
    }

    renderChart() {
        const { chart, labels, values, measure } = this.props.item;
        const isLine = chart === "line";
        this.chart = new window.Chart(this.canvas.el, {
            type: chart,
            data: {
                labels,
                datasets: [
                    {
                        label: measure,
                        data: values,
                        backgroundColor: isLine ? "rgba(31,134,158,.15)" : labels.map((_l, i) => COLORS[i % COLORS.length]),
                        borderColor: isLine ? "#1F869E" : chart === "pie" ? "#fff" : undefined,
                        borderWidth: chart === "bar" ? 0 : 2,
                        fill: isLine,
                        tension: 0.3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: chart === "pie", position: "right", labels: { boxWidth: 10 } } },
                scales: chart === "pie" ? {} : { y: { beginAtZero: true } },
            },
        });
    }
}

export class AiPanel extends Component {
    static template = "technoai_ai.AiPanel";
    static components = { AiChart, Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.ai = useService("technoai_ai");
        this.state = useState(this.ai.state);
        this.ui = useState({ text: "", listening: false });
        this.bodyRef = useRef("body");
        this.inputRef = useRef("input");
        this.formatText = formatText;
        this.suggestions = [
            { icon: "fa-file-text-o", text: _t("Latest purchase order from my top supplier") },
            { icon: "fa-pie-chart", text: _t("Pie chart of sales by customer country") },
            { icon: "fa-bar-chart", text: _t("Bar chart of top-selling products") },
            { icon: "fa-tasks", text: _t("Which tasks are overdue today?") },
        ];
        this.Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        useEffect(
            () => {
                const el = this.bodyRef.el;
                if (el) {
                    el.scrollTop = el.scrollHeight;
                }
            },
            () => [this.state.open, this.state.chat?.items?.length, this.state.busy, this.state.chat?.id]
        );
        useEffect(
            () => {
                if (this.state.open && !this.state.minimized) {
                    this.inputRef.el?.focus();
                }
            },
            () => [this.state.open, this.state.minimized, this.state.busy]
        );
    }

    get items() {
        return this.state.chat?.items || [];
    }

    get lastChat() {
        return this.state.chats[0];
    }

    get resumeChat() {
        return this.state.chats.find((chat) => chat.id !== this.state.chat?.id);
    }

    send(text) {
        const message = (text ?? this.ui.text).trim();
        if (!message || this.state.busy) {
            return;
        }
        this.ui.text = "";
        this.ai.send(message);
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    onInput(ev) {
        this.ui.text = ev.target.value;
        ev.target.style.height = "auto";
        ev.target.style.height = Math.min(ev.target.scrollHeight, 140) + "px";
    }

    change() {
        this.ai.confirm(false, true);
    }

    listen() {
        if (!this.Recognition || this.ui.listening) {
            this.recognition?.stop();
            return;
        }
        const recognition = new this.Recognition();
        recognition.lang = document.documentElement.lang || "en-US";
        recognition.interimResults = true;
        const before = this.ui.text ? this.ui.text + " " : "";
        recognition.onresult = (ev) => {
            this.ui.text = before + [...ev.results].map((r) => r[0].transcript).join("");
        };
        recognition.onend = () => {
            this.ui.listening = false;
            this.inputRef.el?.focus();
        };
        this.recognition = recognition;
        this.ui.listening = true;
        recognition.start();
    }

    cardStateLabel(card) {
        return {
            pending: _t("Confirm"),
            done: _t("Done"),
            cancelled: _t("Cancelled"),
            changed: _t("Changing"),
            failed: _t("Failed"),
        }[card.state];
    }
}

export class AiSystray extends Component {
    static template = "technoai_ai.AiSystray";
    static props = {};

    setup() {
        this.ai = useService("technoai_ai");
        this.state = useState(this.ai.state);
    }
}

registry.category("main_components").add("technoai_ai.AiPanel", { Component: AiPanel });
registry.category("systray").add("technoai_ai.AiSystray", { Component: AiSystray }, { sequence: 30 });
