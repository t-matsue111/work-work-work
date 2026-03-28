/**
 * logs.js - Logs viewer page (Alpine.js)
 */
document.addEventListener('alpine:init', function () {
  Alpine.data('logsApp', function () {
    return {
      logs: [],
      stats: { total_runs: 0, success_rate: 0, total_cost: 0, daily_costs: [] },
      filterStatus: '',
      filterModel: '',
      filterSchedule: '',
      currentOffset: 0,
      PAGE_SIZE: 50,
      showDetailModal: false,
      detailLog: null,

      async init() {
        await this.loadStats();
        await this.loadLogs();
      },

      async loadStats() {
        this.stats = await api.get('/api/logs/stats');
      },

      async loadLogs() {
        var url = '/api/logs?limit=' + this.PAGE_SIZE + '&offset=' + this.currentOffset;
        if (this.filterStatus) url += '&status=' + this.filterStatus;
        if (this.filterModel) url += '&model=' + this.filterModel;
        if (this.filterSchedule) url += '&schedule=' + this.filterSchedule;
        this.logs = await api.get(url);
      },

      resetAndLoad() {
        this.currentOffset = 0;
        this.loadLogs();
      },

      changePage(dir) {
        this.currentOffset = Math.max(0, this.currentOffset + dir * this.PAGE_SIZE);
        this.loadLogs();
      },

      get pageInfo() {
        if (this.logs.length === 0) return '0';
        return (this.currentOffset + 1) + ' - ' + (this.currentOffset + this.logs.length);
      },
      get hasPrev() { return this.currentOffset > 0; },
      get hasNext() { return this.logs.length >= this.PAGE_SIZE; },

      // Daily cost chart
      get chartMaxCost() {
        var costs = this.stats.daily_costs.map(function (d) { return d.cost; });
        return Math.max.apply(null, costs.concat([0.001]));
      },

      chartBarHeight(cost) {
        return Math.max(2, (cost / this.chartMaxCost) * 70) + 'px';
      },

      async openLogDetail(id) {
        var res = await fetch('/api/logs/' + id);
        if (!res.ok) return;
        this.detailLog = await res.json();
        this.showDetailModal = true;
      },

      get detailFields() {
        var log = this.detailLog;
        if (!log) return [];
        return [
          ['Task Name', log.task_name || '-'], ['Timestamp', fmtLocalTime(log.timestamp)],
          ['Status', log.status], ['Model', log.model],
          ['Source', log.task_source], ['Type', log.task_type],
          ['Schedule ID', log.schedule_id || '-'],
          ['Cost', fmtCost(log.cost_usd)], ['Duration', fmtDuration(log.duration_seconds)],
          ['Input Tokens', log.input_tokens], ['Output Tokens', log.output_tokens],
          ['Session ID', log.session_id], ['Runner', log.runner_type],
        ];
      },

      get detailFullFields() {
        var log = this.detailLog;
        if (!log) return [];
        return [
          ['Result Summary', log.result_summary],
          ['Result Detail', log.result_detail],
          ['Error Message', log.error_message],
          ['Raw Response', log.raw_response],
        ];
      },
    };
  });
});
