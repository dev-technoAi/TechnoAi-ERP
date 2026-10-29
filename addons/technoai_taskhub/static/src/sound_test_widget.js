import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { playAlertSound } from "./alert_sounds";

// "Test" button on the Alert sounds form: plays the sound picked on the record
export class TaskhubSoundTest extends Component {
    static template = "technoai_taskhub.SoundTest";
    static props = { ...standardWidgetProps };

    onTest() {
        const { taskhub_alert_sound, taskhub_alert_volume } = this.props.record.data;
        playAlertSound(taskhub_alert_sound || "industrial-siren", taskhub_alert_volume || 80);
    }
}

registry.category("view_widgets").add("taskhub_sound_test", { component: TaskhubSoundTest });
