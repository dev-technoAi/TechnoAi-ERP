import { markup } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { escape } from "@web/core/utils/strings";
import { url } from "@web/core/utils/urls";

const ALERT_MODEL = "rfq.notify.message";
const UNBLOCK_HELP = markup(
    "This browser blocked notifications from Techno AI. Click the lock icon next to the address, " +
        "set <b>Notifications</b> to <b>Allow</b>, then reload the page."
);

/**
 * Asks the browser for notification permission from a button click; once granted, Odoo
 * registers the device for push, so alerts arrive even when the ERP is not open.
 */
async function turnOnNotifications(permission, notification) {
    if (permission.permission === "granted") {
        notification.add("Notifications are already on for this device.", { type: "success" });
    } else if (permission.permission === "denied") {
        notification.add(UNBLOCK_HELP, { type: "warning", title: "Notifications blocked", sticky: true });
    } else {
        await permission.requestPermission();
    }
}

/**
 * New RFQ alerts in an open ERP tab: a sound, a popup with an Open button, and
 * the RFQ Alerts list refreshed in place, so nobody has to reload the page.
 * Mailbox owners whose browser has no notification permission yet are offered
 * a one-click button to turn it on.
 */
export const rfqAlertService = {
    dependencies: ["bus_service", "notification", "action", "orm", "mail.notification.permission"],

    start(env, { bus_service, notification, action, orm, "mail.notification.permission": permission }) {
        const sound = new Audio(url("/mail/static/src/audio/ting.mp3"));

        bus_service.subscribe("technoai_rfq_notify/alert", (payload) => {
            sound.currentTime = 0;
            sound.play().catch(() => {}); // the browser blocks sound until the page was clicked once
            const close = notification.add(markup(`${escape(payload.subject)}<br/>${escape(payload.sender)}`), {
                title: `${payload.title} · ${payload.mailbox}`,
                type: "warning",
                sticky: true,
                buttons: [
                    {
                        name: "Open",
                        primary: true,
                        onClick: () => {
                            close();
                            action.doAction({
                                type: "ir.actions.act_window",
                                res_model: ALERT_MODEL,
                                res_id: payload.id,
                                views: [[false, "form"]],
                            });
                        },
                    },
                ],
            });
            const controller = action.currentController;
            if (controller?.action?.res_model === ALERT_MODEL && controller.view?.type !== "form") {
                action.doAction("soft_reload");
            }
        });

        // offer once per page load, only to people who added a mailbox
        browser.setTimeout(async () => {
            if (permission.permission === "granted" || !browser.Notification) {
                return;
            }
            const mailboxes = await orm.searchCount("rfq.notify.mailbox", [["user_id", "=", user.userId]]);
            if (!mailboxes) {
                return;
            }
            if (permission.permission === "denied") {
                notification.add(UNBLOCK_HELP, { type: "warning", title: "RFQ alerts are blocked on this device" });
                return;
            }
            const close = notification.add(
                "Get a notification with sound on this computer or phone as soon as an RFQ reaches your mailbox, even when the ERP is closed.",
                {
                    title: "Turn on RFQ alerts on this device",
                    type: "info",
                    sticky: true,
                    buttons: [
                        {
                            name: "Turn on",
                            primary: true,
                            onClick: async () => {
                                close();
                                await turnOnNotifications(permission, notification);
                            },
                        },
                        { name: "Later", onClick: () => close() },
                    ],
                }
            );
        }, 4000);

        return { turnOn: () => turnOnNotifications(permission, notification) };
    },
};

registry.category("services").add("technoai_rfq_alert", rfqAlertService);

// menu "Turn on notifications"
registry.category("actions").add("technoai_rfq_notify_turn_on", async (env) => {
    await env.services.technoai_rfq_alert.turnOn();
});
