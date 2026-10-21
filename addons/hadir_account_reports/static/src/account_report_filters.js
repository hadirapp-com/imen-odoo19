/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useService } from "@web/core/utils/hooks";

function toISODate(date) {
    // Local-component formatting: toISOString() shifts the day in UTC+X
    // timezones (Indonesia is UTC+7) because it renders UTC midnight.
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

function displayDate(iso) {
    if (!iso) {
        return "";
    }
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
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

    get isAsOf() {
        return this.filters.date_mode === "as_of";
    }

    applyAsOfPreset(preset) {
        const today = new Date();
        let asOf;
        if (preset === "today") {
            asOf = today;
        } else if (preset === "end_this_month") {
            asOf = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        } else if (preset === "end_last_month") {
            asOf = new Date(today.getFullYear(), today.getMonth(), 0);
        } else if (preset === "end_last_quarter") {
            const quarterStart = new Date(
                today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
            asOf = new Date(quarterStart.getFullYear(),
                quarterStart.getMonth(), 0);
        } else { // end_last_year
            asOf = new Date(today.getFullYear(), 0, 0);
        }
        const iso = toISODate(asOf);
        this.local.dateTo = iso;
        this.local.dateFrom = iso;
        this.props.onDateRange(iso, iso);
    }

    applyCustomAsOf() {
        if (this.local.dateTo) {
            this.local.dateFrom = this.local.dateTo;
            this.props.onDateRange(this.local.dateTo, this.local.dateTo);
        }
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
        if (this.isAsOf) {
            return `As of ${displayDate(df.date_to)}`;
        }
        if (df.date_from === df.date_to) {
            return displayDate(df.date_to);
        }
        return `${displayDate(df.date_from)} → ${displayDate(df.date_to)}`;
    }

    comparisonShortLabel() {
        const mode = this.options.comparison.mode;
        const number = this.options.comparison.number || 1;
        if (this.isAsOf) {
            return mode === "previous_year" ? `Prev. ${number} Year${number > 1 ? "s" : ""}` : "";
        }
        if (mode === "previous_period") {
            return "Prev. Periods";
        }
        if (mode === "previous_year") {
            return "Prev. Years";
        }
        return "";
    }

    entriesLabel() {
        const draft = this.options.all_entries ? "All" : "Posted";
        return `${draft} Entries, Accrual Basis`;
    }
}
