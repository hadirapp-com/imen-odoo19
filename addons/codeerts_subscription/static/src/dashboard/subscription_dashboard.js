/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class SubscriptionDashboard extends Component {
    static template = "codeerts_subscription.Dashboard";
    // Accept the ActionContainer's `className` ("o_action": flex column, height 100%, overflow
    // hidden) so our inner body can be a bounded flex:1 scroller (see .scss). Without this the
    // dashboard does not scroll and clips at the bottom / when zoomed.
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            data: null,
            filters: { period: "last_12m", date_from: null, date_to: null, plan_id: "", team_id: "", user_id: "" },
        });
        this._charts = {};
        this.refs = {
            trend: useRef("trend"),
            movement: useRef("movement"),
            byPlan: useRef("byPlan"),
            topCust: useRef("topCust"),
            movementTrend: useRef("movementTrend"),
            subsTrend: useRef("subsTrend"),
        };
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        // Re-render the charts every time the data changes AND the DOM has been patched
        // (canvases present). Calling renderCharts() manually right after load() runs before
        // OWL re-creates the canvases, leaving the charts blank after Apply/Reset. Same pattern
        // as core web/views/graph/graph_renderer.js.
        useEffect(() => this.renderCharts(), () => [this.state.data]);
        onWillUnmount(() => this.destroyCharts());
    }

    async load() {
        this.state.loading = true;
        const f = this.state.filters;
        this.state.data = await this.orm.call("sale.order", "get_subscription_dashboard_data", [{
            date_from: f.date_from || null,
            date_to: f.date_to || null,
            plan_id: f.plan_id || null,
            team_id: f.team_id || null,
            user_id: f.user_id || null,
        }]);
        this.state.loading = false;
    }

    async apply() {
        await this.load();  // charts re-render via useEffect once the DOM is patched
    }

    async reset() {
        this.state.filters = { period: "last_12m", date_from: null, date_to: null, plan_id: "", team_id: "", user_id: "" };
        await this.load();  // charts re-render via useEffect once the DOM is patched
    }

    // Single "Period" dropdown -> a [from, to] date range (yyyy-mm-dd). "custom" keeps the
    // manual date inputs; "all" spans everything.
    _periodRange(key) {
        const t = new Date();
        const iso = (d) => d.toISOString().slice(0, 10);
        const y = t.getFullYear(), m = t.getMonth();
        switch (key) {
            case "this_month": return [iso(new Date(y, m, 1)), iso(t)];
            case "last_30":    return [iso(new Date(y, m, t.getDate() - 29)), iso(t)];
            case "last_3m":    return [iso(new Date(y, m - 2, 1)), iso(t)];
            case "last_6m":    return [iso(new Date(y, m - 5, 1)), iso(t)];
            case "this_year":  return [iso(new Date(y, 0, 1)), iso(t)];
            case "last_12m":   return [iso(new Date(y, m - 11, 1)), iso(t)];
            case "all":        return [iso(new Date(2000, 0, 1)), iso(t)];
            default:           return [null, null];
        }
    }

    onPeriod(ev) {
        const key = ev.target.value;
        this.state.filters.period = key;
        if (key === "custom") { return; }  // reveal the manual date inputs; user sets them + Apply
        const [from, to] = this._periodRange(key);
        this.state.filters.date_from = from;
        this.state.filters.date_to = to;
        this.apply();
    }

    fmt(v) {
        const c = this.state.data && this.state.data.currency;
        const n = (v || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
        if (!c) return n;
        return c.position === "before" ? `${c.symbol} ${n}` : `${n} ${c.symbol}`;
    }

    // ---- Drill-down helpers (clickable everything) -------------------------
    _subBaseDomain() {
        const f = this.state.data.filters;
        const dom = [["is_subscription", "=", true]];
        if (f.plan_id) { dom.push(["plan_id", "=", f.plan_id]); }
        if (f.team_id) { dom.push(["team_id", "=", f.team_id]); }
        if (f.user_id) { dom.push(["user_id", "=", f.user_id]); }
        return dom;
    }

    openSubs(name, extraDomain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "sale.order",
            domain: [...this._subBaseDomain(), ...(extraDomain || [])],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    openLogs(name, eventType) {
        const f = this.state.data.filters;
        const dom = [];
        if (eventType) { dom.push(["event_type", "=", eventType]); }
        if (f.date_from) { dom.push(["event_date", ">=", f.date_from]); }
        if (f.date_to) { dom.push(["event_date", "<=", f.date_to]); }
        if (f.plan_id) { dom.push(["plan_id", "=", f.plan_id]); }
        if (f.team_id) { dom.push(["team_id", "=", f.team_id]); }
        if (f.user_id) { dom.push(["user_id", "=", f.user_id]); }
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "codeerts.subscription.log",
            domain: dom,
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    onKpi(kind) {
        const t = new Date();
        const today = t.toISOString().slice(0, 10);
        const soon = new Date(t.getTime() + 30 * 86400000).toISOString().slice(0, 10);
        switch (kind) {
            case "mrr":
            case "active":
            case "arpu":
            case "projected":
                return this.openSubs("Active Subscriptions", [["subscription_state", "=", "progress"]]);
            case "paused":
                return this.openSubs("Paused Subscriptions", [["subscription_state", "=", "paused"]]);
            case "new":
                return this.openLogs("New Subscriptions (period)", "0_creation");
            case "churned":
            case "churn_rate":
                return this.openLogs("Churned Subscriptions (period)", "3_churn");
            case "expansion":
                return this.openLogs("Expansion Events (period)", "1_expansion");
            case "issues":
                return this.openSubs("Payment Issues", [["payment_exception", "=", true]]);
            case "renewing":
                return this.openSubs("Renewing in 30 days", [
                    ["subscription_state", "=", "progress"],
                    ["next_invoice_date", ">=", today],
                    ["next_invoice_date", "<=", soon],
                ]);
        }
    }

    onLane(state) {
        const names = { draft: "Quotations", progress: "Active Subscriptions", paused: "Paused Subscriptions",
                        renewed: "Renewed Subscriptions", churn: "Closed Subscriptions" };
        this.openSubs(names[state] || "Subscriptions", [["subscription_state", "=", state]]);
    }

    destroyCharts() {
        for (const k in this._charts) {
            if (this._charts[k]) { this._charts[k].destroy(); }
        }
        this._charts = {};
    }

    renderCharts() {
        if (!this.state.data || typeof Chart === "undefined") { return; }
        this.destroyCharts();
        const d = this.state.data;
        const teal = "#15a89b", navy = "#0b1a2e", indigo = "#6366f1";
        const grid = { color: "rgba(148,163,184,.15)" };
        const pointer = (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; };

        // MRR growth (area line)
        if (this.refs.trend.el) {
            this._charts.trend = new Chart(this.refs.trend.el, {
                type: "line",
                data: {
                    labels: d.mrr_trend.labels,
                    datasets: [{
                        label: "MRR", data: d.mrr_trend.data, fill: true,
                        borderColor: teal, backgroundColor: "rgba(21,168,155,.15)",
                        tension: 0.35, pointRadius: 3, pointBackgroundColor: teal, borderWidth: 2,
                    }],
                },
                options: { responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, grid }, x: { grid: { display: false } } } },
            });
        }
        // MRR movement (colored bar) -> drill into the matching MRR-log events
        if (this.refs.movement.el) {
            const types = ["0_creation", "1_expansion", "2_contraction", "3_churn"];
            this._charts.movement = new Chart(this.refs.movement.el, {
                type: "bar",
                data: {
                    labels: d.movement.labels,
                    datasets: [{ data: d.movement.data,
                        backgroundColor: ["#15a89b", "#6366f1", "#f59e0b", "#ef4444"], borderRadius: 6 }],
                },
                options: { responsive: true, maintainAspectRatio: false,
                    onHover: pointer,
                    onClick: (e, els) => { if (els.length) { this.openLogs(d.movement.labels[els[0].index] + " (period)", types[els[0].index]); } },
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, grid }, x: { grid: { display: false } } } },
            });
        }
        // Revenue by plan (doughnut) -> drill into that plan's active subs
        if (this.refs.byPlan.el) {
            this._charts.byPlan = new Chart(this.refs.byPlan.el, {
                type: "doughnut",
                data: {
                    labels: d.by_plan.labels,
                    datasets: [{ data: d.by_plan.data,
                        backgroundColor: ["#15a89b", "#6366f1", "#f59e0b", "#ef4444", "#0e8377", "#94a3b8", "#22d3ee"] }],
                },
                options: { responsive: true, maintainAspectRatio: false, cutout: "62%",
                    onHover: pointer,
                    onClick: (e, els) => { if (els.length) { const pid = d.by_plan.ids[els[0].index];
                        this.openSubs(d.by_plan.labels[els[0].index], [["subscription_state", "=", "progress"], ["plan_id", "=", pid]]); } },
                    plugins: { legend: { position: "bottom" } } },
            });
        }
        // Top customers (horizontal bar) -> drill into that customer's active subs
        if (this.refs.topCust.el) {
            this._charts.topCust = new Chart(this.refs.topCust.el, {
                type: "bar",
                data: {
                    labels: d.top_customers.labels,
                    datasets: [{ data: d.top_customers.data, backgroundColor: navy, borderRadius: 6 }],
                },
                options: { indexAxis: "y", responsive: true, maintainAspectRatio: false,
                    onHover: pointer,
                    onClick: (e, els) => { if (els.length) { const cid = d.top_customers.ids[els[0].index];
                        this.openSubs(d.top_customers.labels[els[0].index], [["subscription_state", "=", "progress"], ["partner_id", "=", cid]]); } },
                    plugins: { legend: { display: false } },
                    scales: { x: { beginAtZero: true, grid }, y: { grid: { display: false } } } },
            });
        }
        // New vs Churned per month (grouped bar)
        if (this.refs.movementTrend.el) {
            this._charts.movementTrend = new Chart(this.refs.movementTrend.el, {
                type: "bar",
                data: {
                    labels: d.movement_trend.labels,
                    datasets: [
                        { label: "New", data: d.movement_trend.new, backgroundColor: teal, borderRadius: 5 },
                        { label: "Churned", data: d.movement_trend.churned, backgroundColor: "#ef4444", borderRadius: 5 },
                    ],
                },
                options: { responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: "bottom" } },
                    scales: { y: { beginAtZero: true, grid, ticks: { precision: 0 } }, x: { grid: { display: false } } } },
            });
        }
        // Net active subscribers over time (area line)
        if (this.refs.subsTrend.el) {
            this._charts.subsTrend = new Chart(this.refs.subsTrend.el, {
                type: "line",
                data: {
                    labels: d.subs_trend.labels,
                    datasets: [{
                        label: "Active subscribers", data: d.subs_trend.data, fill: true,
                        borderColor: indigo, backgroundColor: "rgba(99,102,241,.15)",
                        tension: 0.35, pointRadius: 3, pointBackgroundColor: indigo, borderWidth: 2,
                    }],
                },
                options: { responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, grid, ticks: { precision: 0 } }, x: { grid: { display: false } } } },
            });
        }
    }
}

registry.category("actions").add("codeerts_subscription_dashboard", SubscriptionDashboard);
