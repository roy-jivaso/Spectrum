import { patch } from "@web/core/utils/patch";
import { DocumentsDetailsPanel } from "@documents/components/documents_details_panel/documents_details_panel";

const { DateTime } = luxon;

patch(DocumentsDetailsPanel.prototype, {
    get expiryDateInputValue() {
        const value = this.props.record.data.expiry_date;
        return value ? value.toISODate() : "";
    },

    async onToggleTrackExpiry(ev) {
        const checked = ev.target.checked;
        const changes = { track_expiry: checked };
        if (!checked) {
            changes.expiry_date = false;
        }
        await this.props.record.update(changes, { save: true });
    },

    async onExpiryDateChange(ev) {
        const value = ev.target.value;
        await this.props.record.update(
            { expiry_date: value ? DateTime.fromISO(value) : false },
            { save: true }
        );
    },
});