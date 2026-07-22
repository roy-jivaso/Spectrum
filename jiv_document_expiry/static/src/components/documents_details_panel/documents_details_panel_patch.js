import { DocumentsDetailsPanel } from "@documents/components/documents_details_panel/documents_details_panel";
import { BooleanField } from "@web/views/fields/boolean/boolean_field";
import { DateTimeField } from "@web/views/fields/datetime/datetime_field";

DocumentsDetailsPanel.components = {
    ...DocumentsDetailsPanel.components,
    BooleanField,
    DateTimeField,
};
