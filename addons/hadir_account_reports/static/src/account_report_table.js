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
        this.props.info.columns.forEach((column, index) => {
            const last = groups[groups.length - 1];
            if (last && last.label === column.period_label) {
                last.span += 1;
            } else {
                groups.push({ label: column.period_label, span: 1, start: index });
            }
        });
        return groups;
    }

    isBlockStart(index) {
        return this.headerGroups.some((group) => group.start === index);
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
