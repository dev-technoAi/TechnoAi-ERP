import { patch } from "@web/core/utils/patch";
import { SIZES, utils } from "@web/core/ui/ui_service";

// keep in sync with $tai-sidebar-width in sidebar.scss
const SIDEBAR_WIDTH = 199;
const XXL_MIN_WIDTH = 1534;

// Views pick their XXL layout (e.g. the chatter beside the form) from the window
// width. The sidebar takes part of that width, so only call it XXL when the space
// next to the sidebar is XXL; narrower windows get Odoo's own XL layout.
patch(utils, {
    getSize() {
        const size = super.getSize();
        if (size === SIZES.XXL && window.innerWidth - SIDEBAR_WIDTH < XXL_MIN_WIDTH) {
            return SIZES.XL;
        }
        return size;
    },
});
