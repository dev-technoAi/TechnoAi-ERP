import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { SwitchCompanyMenu } from "@web/webclient/switch_company_menu/switch_company_menu";

// With a single company there is nothing to switch to, so the company name opens
// that company's settings for admins instead of being a dead button.
patch(SwitchCompanyMenu.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        this.canEditCompany = user.isAdmin;
    },
    openCompany() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.company",
            res_id: this.companyService.currentCompany.id,
            views: [[false, "form"]],
            target: "current",
        });
    },
});
