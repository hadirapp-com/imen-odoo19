/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AccountingDashboard extends Component {
    static template = "hadir_accounting.AccountingDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ data: null, loading: true, error: null });
        onWillStart(async () => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("res.company", "hadir_dashboard_data", [[]]);
            this.state.error = null;
        } catch (error) {
            this.state.error = error;
        } finally {
            this.state.loading = false;
        }
    }

    maxBalance() {
        const balances = this.state.data?.bank_balances || [];
        const values = balances.map((b) => Math.abs(b.balance)).concat([1]);
        return Math.max(...values);
    }

    balanceWidth(balance) {
        return `${Math.max(2, (Math.abs(balance) / this.maxBalance()) * 100)}%`;
    }

    openLink(link) {
        this.actionService.doAction({ id: link.action_id });
    }

    openResModel(model) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }
}

registry.category("actions").add("hadir_accounting_dashboard", AccountingDashboard);
