import { Component } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

/** Administrator shortcuts in the top bar. */
export class ToolsMenu extends Component {
    static template = "technoai_ai.ToolsMenu";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    get debug() {
        return Boolean(this.env.debug);
    }

    toggleDebug() {
        const url = new URL(browser.location.href);
        url.searchParams.set("debug", this.debug ? "" : "1");
        browser.location.href = url.href;
    }

    async regenerateAssets() {
        await this.orm.call("ir.attachment", "regenerate_assets_bundles");
        browser.location.reload();
    }

    openBackups() {
        browser.open("/web/database/manager", "_blank");
    }

    open(xmlid) {
        return this.action.doAction(xmlid);
    }
}

registry.category("systray").add(
    "technoai_ai.ToolsMenu",
    { Component: ToolsMenu, isDisplayed: () => user.isSystem },
    { sequence: 15 }
);
