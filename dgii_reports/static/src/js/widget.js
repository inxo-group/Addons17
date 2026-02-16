/** @odoo-module **/

import { registry } from "@web/core/registry";
import { UrlField } from "@web/views/fields/url/url_field";
import { Component } from "@odoo/owl";

export class DgiiReportsUrlField extends UrlField {
    get href() {
        const v = this.props.value;
        if (!v) return "";
        return `dgii_reports/${v}`;
    }
}

registry.category("fields").add("dgii_reports_url", {
    component: DgiiReportsUrlField,
});
