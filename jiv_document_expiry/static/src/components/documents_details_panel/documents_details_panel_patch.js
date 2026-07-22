import { patch } from "@web/core/utils/patch";
import { DocumentsDetailsPanel } from "@documents/components/documents_details_panel/documents_details_panel";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

patch(DocumentsDetailsPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.expiryState = useState({
            resId: false,
            trackExpiry: false,
            expiryDate: "",
        });
        onWillStart(() => this._loadExpiry(this.props.record));
        onWillUpdateProps((nextProps) => this._loadExpiry(nextProps.record));
    },

    async _loadExpiry(record) {
        const resId = record?.resId;
        if (!resId || typeof resId !== "number") {
            Object.assign(this.expiryState, {
                resId: false,
                trackExpiry: false,
                expiryDate: "",
            });
            return;
        }
        if (resId === this.expiryState.resId) {
            return; // same document still focused, keep current state
        }
        try {
            const [vals] = await this.orm.read(
                "documents.document",
                [resId],
                ["track_expiry", "expiry_date"]
            );
            Object.assign(this.expiryState, {
                resId,
                trackExpiry: !!vals.track_expiry,
                expiryDate: vals.expiry_date || "",
            });
        } catch {
            Object.assign(this.expiryState, {
                resId: false,
                trackExpiry: false,
                expiryDate: "",
            });
        }
    },

    async onToggleTrackExpiry(ev) {
        const checked = ev.target.checked;
        const vals = { track_expiry: checked };
        if (!checked) {
            vals.expiry_date = false;
        }
        await this.orm.write("documents.document", [this.expiryState.resId], vals);
        this.expiryState.trackExpiry = checked;
        if (!checked) {
            this.expiryState.expiryDate = "";
        }
    },

    async onExpiryDateChange(ev) {
        const value = ev.target.value || false;
        await this.orm.write("documents.document", [this.expiryState.resId], {
            expiry_date: value,
        });
        this.expiryState.expiryDate = value || "";
    },
});