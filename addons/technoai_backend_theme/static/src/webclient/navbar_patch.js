import { onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

// Odoo menus carry no icon, so the sidebar picks one per app and per section
const APP_ICONS = {
    "sale.sale_menu_root": "fa-shopping-bag",
    "purchase.menu_purchase_root": "fa-shopping-basket",
    "account.menu_finance": "fa-money",
    "crm.crm_menu_root": "fa-handshake-o",
    "stock.menu_stock_root": "fa-cubes",
    "project.menu_main_pm": "fa-tasks",
    "contacts.menu_contacts": "fa-address-book",
    "calendar.mail_menu_calendar": "fa-calendar",
    "mail.menu_root_discuss": "fa-comments",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root": "fa-th-large",
    "utm.menu_link_tracker_root": "fa-link",
    "base.menu_management": "fa-th",
    "base.menu_administration": "fa-sliders",
    "technoai_sso.menu_taskhub_root": "fa-check-square-o",
};

const SECTION_ICONS = {
    "account.menu_board_journal_1": "fa-tachometer",
    "account.menu_finance_receivables": "fa-user",
    "account.menu_finance_payables": "fa-truck",
    "account.menu_finance_entries": "fa-book",
    "crm.crm_menu_sales": "fa-line-chart",
    "crm.crm_menu_leads": "fa-bullseye",
    "crm.menu_import_crm": "fa-refresh",
    "sale.sale_order_menu": "fa-shopping-cart",
    "sale.menu_sale_invoicing": "fa-file-text",
    "purchase.menu_procurement_management": "fa-shopping-cart",
    "stock.stock_picking_type_menu": "fa-tachometer",
    "stock.menu_stock_warehouse_mgmt": "fa-exchange",
    "project.menu_projects": "fa-folder-open",
    "project.menu_projects_group_stage": "fa-folder-open",
    "project.menu_project_management": "fa-tasks",
    "contacts.res_partner_menu_contacts": "fa-address-book",
    "calendar.calendar_event_menu": "fa-calendar",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_dashboard": "fa-th-large",
    "utm.marketing_utm": "fa-link",
    "base.menu_apps": "fa-th",
    "base.menu_view_base_module_update": "fa-refresh",
    "base.menu_view_base_module_upgrade": "fa-level-up",
    "base_import_module.menu_view_base_module_import": "fa-upload",
    "base_setup.menu_config": "fa-cogs",
    "base.menu_config": "fa-cogs",
    "base.menu_users": "fa-users",
    "base.menu_translation": "fa-language",
    "base.menu_administration_shortcut": "fa-keyboard-o",
    "base.menu_custom": "fa-wrench",
};

// fallback for sections of apps installed later, matched on the menu's xmlid
const SECTION_KEYWORDS = [
    [/config/, "fa-cog"],
    [/report/, "fa-bar-chart"],
    [/product|catalog/, "fa-cube"],
    [/order|sale/, "fa-shopping-cart"],
    [/invoic|bill/, "fa-file-text"],
    [/customer|partner|contact/, "fa-user"],
    [/vendor|supplier/, "fa-truck"],
    [/employee|user|team/, "fa-users"],
    [/dashboard|overview/, "fa-tachometer"],
    [/calendar|planning|schedul/, "fa-calendar"],
];

patch(NavBar.prototype, {
    setup() {
        super.setup();
        // lets the stylesheet lay out the sidebar only while the navbar is shown
        // (fullscreen actions hide it)
        onMounted(() => document.body.classList.add("o_tai_sidebar"));
        onWillUnmount(() => document.body.classList.remove("o_tai_sidebar"));
    },

    async adapt() {
        if (!this.ui.isSmall) {
            // the sidebar lists every section, so none goes into the "More" overflow menu
            if (this.currentAppSectionsExtra.length) {
                this.currentAppSectionsExtra = [];
                this.render();
            }
            return;
        }
        return super.adapt();
    },

    taiAppIcon(app) {
        return APP_ICONS[app?.xmlid] || "fa-th-large";
    },

    taiSectionIcon(section) {
        const xmlid = section.xmlid || "";
        if (SECTION_ICONS[xmlid]) {
            return SECTION_ICONS[xmlid];
        }
        const name = xmlid.split(".").pop().toLowerCase();
        const match = SECTION_KEYWORDS.find(([pattern]) => pattern.test(name));
        return match ? match[1] : "fa-folder-o";
    },
});
