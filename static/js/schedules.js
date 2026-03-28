/**
 * schedules.js - Schedules management page (Alpine.js)
 */
document.addEventListener('alpine:init', function () {
  Alpine.data('schedulesApp', function () {
    return {
      schedules: [],
      editingId: null,
      showModal: false,
      promptFiles: [],
      form: {},

      async init() {
        var self = this;
        registerPageShortcuts({
          new: function() { self.openAdd(); },
          modalDelete: function() { if (self.showModal && self.editingId) self.deleteEditing(); },
        });
        await this.loadSchedules();
        await this.loadPromptFiles();
        setInterval(() => this.loadSchedules(), 30000);
      },

      resetForm() {
        this.form = {
          name: '', cron_expr: '', cron_preset: '', task_type: '', priority: 'medium',
          backend: 'claude', model: 'sonnet', prompt: '', prompt_file: '',
          mcp_config: '', tools_preset: '', allowed_tools: '',
          timeout_seconds: 300, max_turns: 30, max_consecutive_failures: 3,
          session_persistent: 0, work_dir: '',
        };
      },

      async loadSchedules() {
        this.schedules = await api.get('/api/schedules');
      },

      async loadPromptFiles() {
        try {
          var prompts = await api.get('/api/prompts');
          this.promptFiles = prompts;
        } catch (e) {
          this.promptFiles = [];
        }
      },

      openAddModal() {
        this.editingId = null;
        this.resetForm();
        this.showModal = true;
        this.$nextTick(function () {
          var el = document.getElementById('addName');
          if (el) el.focus();
        });
      },

      async openEdit(id) {
        var res = await fetch('/api/schedules/' + id);
        if (!res.ok) return;
        var s = await res.json();
        this.editingId = id;
        this.form = {
          name: s.name || '',
          cron_expr: s.cron_expr || '',
          cron_preset: '',
          task_type: s.task_type || '',
          priority: s.priority || 'medium',
          backend: s.backend || 'claude',
          model: s.model || 'sonnet',
          prompt: s.prompt || '',
          prompt_file: s.prompt_file || '',
          mcp_config: s.mcp_config || '',
          tools_preset: '',
          allowed_tools: s.allowed_tools || '',
          timeout_seconds: s.timeout_seconds || 300,
          max_turns: s.max_turns || 30,
          max_consecutive_failures: s.max_consecutive_failures || 3,
          session_persistent: s.session_persistent || 0,
          work_dir: s.work_dir || '',
        };
        this.showModal = true;
      },

      async toggleEnabled(id, newVal) {
        await api.patch('/api/schedules/' + id, { enabled: newVal });
        this.loadSchedules();
      },

      async triggerRun(id) {
        await api.post('/api/schedules/' + id + '/trigger', {});
        this.loadSchedules();
      },

      applyCronPreset() {
        if (this.form.cron_preset) {
          this.form.cron_expr = this.form.cron_preset;
        }
      },

      applyToolsPreset() {
        this.form.allowed_tools = this.form.tools_preset;
      },

      async submitForm() {
        if (!this.form.name.trim()) return alert('\u540d\u524d\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044');
        if (!this.form.cron_expr.trim()) return alert('cron\u5f0f\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044');
        var body = {
          name: this.form.name,
          cron_expr: this.form.cron_expr,
          task_type: this.form.task_type,
          priority: this.form.priority,
          backend: this.form.backend,
          model: this.form.model || 'sonnet',
          description: '',
          prompt: this.form.prompt,
          prompt_file: this.form.prompt_file,
          timeout_seconds: parseInt(this.form.timeout_seconds) || 300,
          max_turns: parseInt(this.form.max_turns) || 30,
          work_dir: this.form.work_dir,
          mcp_config: this.form.mcp_config,
          allowed_tools: this.form.allowed_tools,
          max_consecutive_failures: parseInt(this.form.max_consecutive_failures) || 3,
          session_persistent: parseInt(this.form.session_persistent) || 0,
        };
        var res;
        if (this.editingId) {
          res = await api.patch('/api/schedules/' + this.editingId, body);
        } else {
          res = await api.post('/api/schedules', body);
        }
        if (!res.ok) {
          var e = await res.json();
          return alert('\u30a8\u30e9\u30fc: ' + (e.error || 'Unknown'));
        }
        this.showModal = false;
        this.loadSchedules();
      },

      async deleteEditing() {
        if (!this.editingId) return;
        if (!confirm('\u3053\u306e\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u3092\u524a\u9664\u3057\u307e\u3059\u304b\uff1f')) return;
        await api.del('/api/schedules/' + this.editingId);
        this.showModal = false;
        this.loadSchedules();
      },
    };
  });
});
