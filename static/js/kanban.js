/**
 * kanban.js - Kanban board (Alpine.js data + vanilla drag-and-drop)
 */
document.addEventListener('alpine:init', function () {
  Alpine.data('kanbanApp', function () {
    return {
      tasks: [],
      stats: { total: 0, completion_rate: 0 },
      // Add modal
      addForm: {
        task_name: '', task_type: 'research', priority: 'medium', input: '',
        model: '', mcp_config: '', timeout_seconds: '', max_turns: '',
        work_dir: '', allowed_tools: '',
      },
      showAddModal: false,
      // Detail modal
      showDetailModal: false,
      detailTask: null,

      STATUS_MAP: {
        pending: 'col-pending',
        in_progress: 'col-in_progress',
        completed: 'col-completed',
        error: 'col-error',
        needs_clarification: 'col-review',
        needs_review: 'col-review',
      },

      async init() {
        var self = this;
        registerPageShortcuts({
          new: function() { self.showAddModal = true; },
          modalDelete: function() { if (self.showDetailModal && self.detailTask) self.deleteTask(self.detailTask.id); },
          modalArchive: function() { if (self.showDetailModal && self.detailTask && (self.detailTask.status === 'completed' || self.detailTask.status === 'error')) self.archiveTask(self.detailTask.id); },
        });
        await this.loadTasks();
        this.setupDragDrop();
        setInterval(() => this.loadTasks(), 30000);
      },

      async loadTasks() {
        this.tasks = await api.get('/api/tasks');
        this.renderBoard();
        var s = await api.get('/api/stats');
        this.stats = s;
      },

      tasksForColumn(colStatus) {
        if (colStatus === 'needs_review') {
          return this.tasks.filter(function (t) {
            return t.status === 'needs_review' || t.status === 'needs_clarification';
          });
        }
        return this.tasks.filter(function (t) { return t.status === colStatus; });
      },

      renderBoard() {
        var self = this;
        // カード描画 (vanilla DOM for drag-drop compatibility)
        var colIds = ['col-pending', 'col-in_progress', 'col-completed', 'col-error', 'col-review'];
        colIds.forEach(function (id) {
          var el = document.getElementById(id);
          if (el) el.innerHTML = '';
        });

        var counts = { pending: 0, in_progress: 0, completed: 0, error: 0, review: 0 };
        self.tasks.forEach(function (t) {
          var colId = self.STATUS_MAP[t.status];
          if (!colId) return;
          var col = document.getElementById(colId);
          if (!col) return;
          col.appendChild(self.createCard(t));
          if (t.status === 'needs_clarification' || t.status === 'needs_review') counts.review++;
          else if (counts[t.status] !== undefined) counts[t.status]++;
        });

        document.getElementById('cnt-pending').textContent = counts.pending;
        document.getElementById('cnt-in_progress').textContent = counts.in_progress;
        document.getElementById('cnt-completed').textContent = counts.completed;
        document.getElementById('cnt-error').textContent = counts.error;
        document.getElementById('cnt-review').textContent = counts.review;
      },

      createCard(task) {
        var self = this;
        var div = document.createElement('div');
        div.className = 'card';
        div.draggable = true;
        div.dataset.id = task.id;
        div.dataset.status = task.status;
        div.innerHTML =
          '<div class="card-title">' + esc(task.task_name) + '</div>' +
          '<div class="card-meta">' +
          '  <span class="' + badgeClass(task.task_type) + '">' + task.task_type + '</span>' +
          '  <span class="priority-dot priority-' + task.priority + '" title="' + task.priority + '"></span>' +
          '</div>' +
          '<div class="card-time">' + relativeTime(task.created_at) + '</div>';
        div.addEventListener('dragstart', function (e) {
          e.dataTransfer.setData('text/plain', task.id);
          div.classList.add('dragging');
        });
        div.addEventListener('dragend', function () {
          div.classList.remove('dragging');
        });
        div.addEventListener('click', function () {
          self.openDetail(task);
        });
        return div;
      },

      setupDragDrop() {
        var self = this;
        document.querySelectorAll('.kanban-column-body').forEach(function (col) {
          col.addEventListener('dragover', function (e) {
            e.preventDefault();
            col.classList.add('drag-over');
          });
          col.addEventListener('dragleave', function () {
            col.classList.remove('drag-over');
          });
          col.addEventListener('drop', async function (e) {
            e.preventDefault();
            col.classList.remove('drag-over');
            var id = e.dataTransfer.getData('text/plain');
            var newStatus = col.closest('.kanban-column').dataset.status;
            await api.patch('/api/tasks/' + id, { status: newStatus });
            self.loadTasks();
          });
        });
      },

      openAddModal() {
        this.addForm = {
          task_name: '', task_type: 'research', priority: 'medium', input: '',
          model: '', mcp_config: '', timeout_seconds: '', max_turns: '',
          work_dir: '', allowed_tools: '',
        };
        this.showAddModal = true;
        this.$nextTick(function () {
          var el = document.getElementById('addName');
          if (el) el.focus();
        });
      },

      async submitAdd() {
        var f = this.addForm;
        if (!f.task_name.trim()) return alert('\u30bf\u30b9\u30af\u540d\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044');
        var body = {
          task_name: f.task_name,
          task_type: f.task_type || 'research',
          priority: f.priority,
          input: f.input,
        };
        if (f.model) body.model = f.model;
        if (f.mcp_config) body.mcp_config = f.mcp_config;
        if (f.timeout_seconds) body.timeout_seconds = parseInt(f.timeout_seconds);
        if (f.max_turns) body.max_turns = parseInt(f.max_turns);
        if (f.work_dir) body.work_dir = f.work_dir;
        if (f.allowed_tools) body.allowed_tools = f.allowed_tools;
        await api.post('/api/tasks', body);
        this.showAddModal = false;
        this.loadTasks();
      },

      openDetail(task) {
        this.detailTask = task;
        this.showDetailModal = true;
      },

      async deleteTask() {
        if (!this.detailTask) return;
        if (!confirm('\u3053\u306e\u30bf\u30b9\u30af\u3092\u524a\u9664\u3057\u307e\u3059\u304b\uff1f')) return;
        await api.del('/api/tasks/' + this.detailTask.id);
        this.showDetailModal = false;
        this.loadTasks();
      },

      async archiveTask() {
        if (!this.detailTask) return;
        await api.patch('/api/tasks/' + this.detailTask.id, { archived: 1 });
        this.showDetailModal = false;
        this.loadTasks();
      },

      canArchive() {
        return this.detailTask && (this.detailTask.status === 'completed' || this.detailTask.status === 'error');
      },
    };
  });
});
