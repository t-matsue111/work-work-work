/**
 * tasks.js - Tasks list page (Alpine.js)
 */
document.addEventListener('alpine:init', function () {
  Alpine.data('tasksApp', function () {
    return {
      tasks: [],
      filterStatus: '',
      filterArchived: 'active',
      currentOffset: 0,
      PAGE_SIZE: 50,
      totalCount: 0,

      async init() {
        var self = this;
        registerPageShortcuts({
          prev: function() { if (self.hasPrev) self.changePage(-1); },
          next: function() { if (self.hasNext) self.changePage(1); },
        });
        await this.loadTasks();
      },

      async loadTasks() {
        var arch = this.filterArchived;
        var url = '/api/tasks?archived=' + (arch === 'all' ? '1' : arch === 'archived' ? '1' : '0');
        var tasks = await api.get(url);
        if (this.filterStatus) {
          tasks = tasks.filter(function (t) { return t.status === this.filterStatus; }.bind(this));
        }
        if (arch === 'archived') {
          tasks = tasks.filter(function (t) { return t.archived === 1; });
        } else if (arch === 'active') {
          tasks = tasks.filter(function (t) { return !t.archived; });
        }
        this.totalCount = tasks.length;
        this.tasks = tasks.slice(this.currentOffset, this.currentOffset + this.PAGE_SIZE);
      },

      changePage(dir) {
        this.currentOffset = Math.max(0, this.currentOffset + dir * this.PAGE_SIZE);
        this.loadTasks();
      },

      resetAndLoad() {
        this.currentOffset = 0;
        this.loadTasks();
      },

      get pageInfo() {
        if (this.tasks.length === 0) return '0';
        return (this.currentOffset + 1) + ' - ' + (this.currentOffset + this.tasks.length) + ' / ' + this.totalCount;
      },

      get hasPrev() { return this.currentOffset > 0; },
      get hasNext() { return this.currentOffset + this.PAGE_SIZE < this.totalCount; },

      async archive(id) {
        await api.patch('/api/tasks/' + id, { archived: 1 });
        this.loadTasks();
      },

      async unarchive(id) {
        await api.patch('/api/tasks/' + id, { archived: 0 });
        this.loadTasks();
      },
    };
  });
});
