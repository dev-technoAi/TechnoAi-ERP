import { Component, onMounted, onWillUnmount, useExternalListener, xml } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

const HOME_TAG = "technoai_home";

/** Page behind the apps launcher; while it is shown, the launcher stays open. */
class TechnoaiHome extends Component {
    static template = xml`<div class="o_tai_home_action"/>`;
    static props = ["*"];

    setup() {
        onMounted(() => this.env.bus.trigger("TECHNOAI:HOME", true));
        onWillUnmount(() => this.env.bus.trigger("TECHNOAI:HOME", false));
    }
}

registry.category("actions").add(HOME_TAG, TechnoaiHome);

// The built-in "home" client action (reload to the root) has the same name as the launcher's
// path, so it is the one that /technoai/home finds. Coming from that URL, open the launcher;
// everywhere else it keeps its own behaviour.
const actions = registry.category("actions");
const builtinHome = actions.get("home");
actions.add(
    "home",
    (env, action) => {
        if (action?.params?.action === "home") {
            return { type: "ir.actions.client", tag: HOME_TAG, name: "Home", path: "home" };
        }
        return builtinHome(env, action);
    },
    { force: true }
);

patch(NavBar.prototype, {
    setup() {
        super.setup();
        useBus(this.env.bus, "TECHNOAI:HOME", ({ detail: open }) => {
            if (open !== this.state.isHomeMenuOpened) {
                super.toggleHomeMenu(open);
            }
        });
        // Escape closes the launcher in the navbar itself; then leave the home page too
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key === "Escape" && !this.state.isHomeMenuOpened && this.taiOnHomePage) {
                this.taiLeaveHome();
            }
        });
    },

    get taiOnHomePage() {
        return this.actionService.currentController?.action?.tag === HOME_TAG;
    },

    toggleHomeMenu(force) {
        const open = typeof force === "boolean" ? force : !this.state.isHomeMenuOpened;
        super.toggleHomeMenu(open);
        if (open && !this.taiOnHomePage) {
            // its own clean address, /technoai/home; the page it came from stays in the browser history
            this.taiCameFromPage = true;
            this.actionService.doAction("technoai_backend_theme.action_home", { clearBreadcrumbs: true });
        } else if (!open && this.taiOnHomePage) {
            this.taiLeaveHome();
        }
    },

    /** Back to the page the launcher was opened from, or to the first app after a refresh. */
    taiLeaveHome() {
        if (this.taiCameFromPage) {
            this.taiCameFromPage = false;
            browser.history.back();
            return;
        }
        const app = this.orderedApps?.[0] || this.menuService.getApps()[0];
        if (app) {
            this.onNavBarDropdownItemSelection(app);
        }
    },
});
