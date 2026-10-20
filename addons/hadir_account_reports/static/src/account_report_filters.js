/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useService } from "@web/core/utils/hooks";

function toISODate(date) {
    return date.toISOString().slice(0, 10);
}

export class AccountReportFilters extends Component {
    static template = "hadir_account_reports.AccountReportFilters";
    static components = { Dropdown, DropdownItem };
    static props = {
        info: Object,
        onDateRange: Function,
        onComparison: Function,
        onMonthlyMode: Function,
        onJournals: Function,
        onPartners: Function,
        onAllEntries: Function,
        onUnfoldAll: Function,
        onConsolidation: Function,
        onElimination: Function,
        onSwitchReport: Function,
        onPrintPdf: Function,
        onExportXlsx: Function,
    };

    setup() {
        this.orm = useService("orm");
        const dateFilter = this.props.info.options.date_filter || {};
        this.local = useState({
            dateFrom: dateFilter.date_from || "",
            dateTo: dateFilter.date_to || "",
            comparisonNumber: this.props.info.options.comparison.number || 1,
            partnerSearch: "",
            partners: [],
        });
    }

    get options() {
        return this.props.info.options;
    }

    get filters() {
        return this.props.info.filters || {};
    }

    applyPreset(preset) {
        const today = new Date();
        let dateFrom;
        if (preset === "month") {
            dateFrom = new Date(today.getFullYear(), today.getMonth(), 1);
        } else if (preset === "quarter") {
            dateFrom = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
        } else {
            dateFrom = new Date(today.getFullYear(), 0, 1);
        }
        this.local.dateFrom = toISODate(dateFrom);
        this.local.dateTo = toISODate(today);
        this.props.onDateRange(this.local.dateFrom, this.local.dateTo);
    }

    applyCustomRange() {
        if (this.local.dateFrom && this.local.dateTo) {
            this.props.onDateRange(this.local.dateFrom, this.local.dateTo);
        }
    }

    setComparison(mode) {
        this.props.onComparison({ mode, number: Number(this.local.comparisonNumber) || 1 });
    }

    onComparisonNumberChange(ev) {
        this.local.comparisonNumber = ev.target.value;
    }

    onJournalToggle(journal, ev) {
        const selected = new Set(this.options.journals || []);
        if (ev.target.checked) {
            selected.add(journal.id);
        } else {
            selected.delete(journal.id);
        }
        this.props.onJournals([...selected]);
    }

    async searchPartners() {
        try {
            this.local.partners = await this.orm.call(
                "account.report",
                "hpr_search_partners",
                [
                    this.local.partnerSearch || "",
                    20,
                    this.options.partners || [],
                    this.props.info.report.dynamic === "partner_statement",
                ],
            );
        } catch {
            this.local.partners = [];
        }
    }

    onPartnerToggle(partner, ev) {
        const selected = new Set(this.options.partners || []);
        if (ev.target.checked) {
            selected.add(partner.id);
        } else {
            selected.delete(partner.id);
        }
        this.props.onPartners([...selected]);
    }

    dateShortLabel() {
        const df = this.options.date_filter || {};
        if (!df.date_from) {
            return "";
        }
        if (df.date_from === df.date_to) {
            return df.date_to;
        }
        return `${df.date_from} → ${df.date_to}`;
    }
}
