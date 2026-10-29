import { reactive } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

const MODEL = "technoai.ai.chat";

/**
 * Shared state of the assistant: the systray button and the panel both read it.
 * The conversation itself lives on the server (technoai.ai.chat).
 */
export const aiService = {
    dependencies: ["orm", "action"],
    start(env, { orm, action }) {
        const state = reactive({
            open: false,
            minimized: false,
            expanded: false,
            status: null, // {configured, is_admin}
            chat: null, // {id, name, items, pending}
            chats: [],
            showResume: false,
            busy: false,
            draft: null, // the message being answered, shown before the server replies
            localError: null,
        });

        function currentPage() {
            const controller = action.currentController;
            if (!controller) {
                return null;
            }
            return {
                title: controller.displayName || controller.action?.name || "",
                model: controller.props?.resModel || false,
                res_id: controller.props?.resId || false,
            };
        }

        async function call(method, args) {
            state.localError = null;
            try {
                return await orm.silent.call(MODEL, method, args);
            } catch (error) {
                state.localError = error.data?.message || error.message || _t("Something went wrong.");
                return null;
            }
        }

        async function refreshChats() {
            state.chats = (await call("ai_list_chats", [])) || [];
        }

        return {
            state,
            async toggle() {
                if (state.open && !state.minimized) {
                    state.open = false;
                    return;
                }
                state.open = true;
                state.minimized = false;
                if (!state.status) {
                    state.status = await call("ai_status", []);
                    await refreshChats();
                    state.showResume = Boolean(state.chats.length && !state.chat);
                }
            },
            close() {
                state.open = false;
            },
            newChat() {
                state.chat = null;
                state.showResume = false;
                state.localError = null;
            },
            async openChat(chatId) {
                const chat = await call("ai_load", [[chatId]]);
                if (chat) {
                    state.chat = chat;
                }
                state.showResume = false;
            },
            refreshChats,
            async send(text) {
                if (state.busy || !text.trim()) {
                    return;
                }
                state.busy = true;
                state.showResume = false;
                state.draft = text.trim();
                try {
                    const chat = await call("ai_send", [state.chat?.id || false, text, currentPage()]);
                    if (chat) {
                        state.chat = chat;
                    }
                } finally {
                    state.busy = false;
                    state.draft = null;
                }
                refreshChats();
            },
            async confirm(approve, change = false) {
                if (state.busy || !state.chat) {
                    return;
                }
                state.busy = true;
                try {
                    const chat = await call("ai_confirm", [[state.chat.id], approve, change]);
                    if (chat) {
                        state.chat = chat;
                    }
                } finally {
                    state.busy = false;
                }
            },
            openRecord(resModel, resId) {
                return action.doAction({
                    type: "ir.actions.act_window",
                    res_model: resModel,
                    res_id: resId,
                    views: [[false, "form"]],
                });
            },
            openLink(item) {
                const views = item.view_type === "form" ? [[false, "form"]] : [[false, item.view_type], [false, "form"]];
                return action.doAction({
                    type: "ir.actions.act_window",
                    name: item.title || item.label,
                    res_model: item.model,
                    res_id: item.record_id || undefined,
                    domain: item.domain || [],
                    views,
                });
            },
            openChart(item) {
                const { model, domain, groupby, measure } = item.action;
                const context = { graph_measure: measure || "__count", graph_mode: item.chart };
                if (!groupby.includes(".")) {
                    context.graph_groupbys = [groupby];
                }
                return action.doAction({
                    type: "ir.actions.act_window",
                    name: item.title || _t("Analysis"),
                    res_model: model,
                    domain,
                    context,
                    views: [[false, "graph"], [false, "list"]],
                });
            },
        };
    },
};

registry.category("services").add("technoai_ai", aiService);
