/** @odoo-module **/
import { Component } from "@odoo/owl";

export class AccountReportTable extends Component {
    static template = "hadir_account_reports.AccountReportTable";
    static props = {
        info: Object,
        onToggleLine: Function,
        onOpenLine: Function,
    };

    get headerGroups() {
        const groups = [];
        for (const column of this.props.info.columns) {
            const last = groups[groups.length - 1];
            if (last && last.label === column.period_label) {
                last.span += 1;
            } else {
                groups.push({ label: column.period_label, span: 1 });
            }
        }
        return groups;
    }

    colsPerPeriod() {
        const groups = this.headerGroups;
        return groups.length ? Math.ceil(this.props.info.columns.length / groups.length) : 1;
    }

    onRowClick(line, ev) {
        if (line.foldable) {
            this.props.onToggleLine(line);
        } else if (line.action_id) {
            this.props.onOpenLine(line);
        }
    }

    rowClass(line) {
        return line.classes.join(" ");
    }
}
