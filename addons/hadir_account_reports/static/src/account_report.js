/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { AccountReportFilters } from "./account_report_filters";
import { AccountReportTable } from "./account_report_table";

export class AccountReport extends Component {
    static template = "hadir_account_reports.AccountReport";
    static components = { AccountReportFilters, AccountReportTable };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ info: null, loading: true, error: null });
        onWillStart(async () => {
            try {
                await this.load();
            } catch (error) {
                this.state.error = error.message || error.data?.name || "Failed to load report";
                this.state.loading = false;
            }
        });
    }

    get options() {
        return this.state.info ? this.state.info.options : {};
    }

    initialOptions() {
        const action = this.props.action || {};
        let reportId = null;
        const ctx = action.context;
        if (ctx && typeof ctx === "object") {
            reportId = ctx.report_id;
        } else if (typeof ctx === "string") {
            const match = ctx.match(/'report_id':\s*(\d+)/);
            if (match) {
                reportId = parseInt(match[1], 10);
            }
        }
        if (!reportId && action.params && typeof action.params === "object") {
            reportId = action.params.report_id;
        }
        return { report_id: reportId };
    }

    async load(options) {
        this.state.loading = true;
        try {
            this.state.info = await this.orm.call(
                "account.report",
                "get_report_informations",
                [options || this.initialOptions()],
            );
        } finally {
            this.state.loading = false;
        }
    }

    async applyOptions(patch) {
        await this.load({ ...this.options, ...patch });
    }

    onDateRange(dateFrom, dateTo) {
        return this.applyOptions({ date_filter: { date_from: dateFrom, date_to: dateTo } });
    }

    onComparison(comparison) {
        return this.applyOptions({ comparison });
    }

    onMonthlyMode(monthlyMode) {
        return this.applyOptions({ monthly_mode: monthlyMode });
    }

    onJournals(journals) {
        return this.applyOptions({ journals });
    }

    onPartners(partners) {
        return this.applyOptions({ partners });
    }

    onAllEntries(allEntries) {
        return this.applyOptions({ all_entries: allEntries });
    }

    onUnfoldAll(unfoldAll) {
        return this.applyOptions({ unfold_all: unfoldAll });
    }

    onConsolidation(enabled) {
        return this.applyOptions({ hadir_consolidation: enabled });
    }

    onElimination(enabled) {
        return this.applyOptions({ hadir_elimination: enabled });
    }

    onToggleLine(line) {
        const unfolded = { ...(this.options.unfolded_lines || {}) };
        if (unfolded[line.id]) {
            delete unfolded[line.id];
        } else {
            unfolded[line.id] = true;
        }
        return this.applyOptions({ unfolded_lines: unfolded });
    }

    onOpenLine(line) {
        if (line.action_id) {
            this.actionService.doAction(line.action_id);
        }
    }

    onSwitchReport(item) {
        return this.applyOptions({ report_id: item.report_id, unfolded_lines: {} });
    }

    async printPdf() {
        await this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "hadir_account_reports.report_hpr",
            report_file: "hadir_account_reports.report_hpr",
            data: {
                report_id: this.options.report_id,
                options: JSON.parse(JSON.stringify(this.options)),
            },
            display_name: this.state.info.report.name,
        });
    }

    async exportXlsx() {
        const result = await rpc("/hadir_account_reports/export/xlsx", {
            options: JSON.parse(JSON.stringify(this.options)),
        });
        if (result && result.file_base64) {
            const link = document.createElement("a");
            link.href = `data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${result.file_base64}`;
            link.download = result.file_name;
            document.body.appendChild(link);
            link.click();
            link.remove();
        }
    }
}

registry.category("actions").add("account_report", AccountReport);
