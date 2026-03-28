/**
 * prompts.js - Prompts management page (Alpine.js)
 */
document.addEventListener('alpine:init', function () {
  Alpine.data('promptsApp', function () {
    return {
      prompts: [],
      editingFile: null,
      showModal: false,
      form: { name: '', content: '' },
      nameDisabled: false,

      async init() {
        var self = this;
        registerPageShortcuts({
          new: function() { self.openNew(); },
          modalDelete: function() { if (self.showModal && self.editingFile) self.deletePrompt(); },
        });
        await this.loadPrompts();
      },

      async loadPrompts() {
        this.prompts = await api.get('/api/prompts');
      },

      openNewModal() {
        this.editingFile = null;
        this.form = { name: '', content: '' };
        this.nameDisabled = false;
        this.showModal = true;
        this.$nextTick(function () {
          var el = document.getElementById('editName');
          if (el) el.focus();
        });
      },

      async openEditModal(name) {
        var res = await fetch('/api/prompts/' + encodeURIComponent(name));
        if (!res.ok) return;
        var p = await res.json();
        this.editingFile = name;
        this.form = {
          name: name.replace(/\.txt$/, ''),
          content: p.content || '',
        };
        this.nameDisabled = true;
        this.showModal = true;
        this.$nextTick(function () {
          var el = document.getElementById('editContent');
          if (el) el.focus();
        });
      },

      async savePrompt() {
        var name = this.form.name.trim();
        var content = this.form.content;
        if (!name) return alert('\u30d5\u30a1\u30a4\u30eb\u540d\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044');
        if (!name.endsWith('.txt')) name += '.txt';
        if (!/^[a-zA-Z0-9_\-]+\.txt$/.test(name)) return alert('\u30d5\u30a1\u30a4\u30eb\u540d\u306f\u82f1\u6570\u5b57\u30fb\u30cf\u30a4\u30d5\u30f3\u30fb\u30a2\u30f3\u30c0\u30fc\u30b9\u30b3\u30a2\u306e\u307f\u3067\u3059');
        var method, url;
        if (this.editingFile) {
          method = 'PUT';
          url = '/api/prompts/' + encodeURIComponent(this.editingFile);
        } else {
          method = 'POST';
          url = '/api/prompts';
        }
        var res = await fetch(url, {
          method: method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name, content: content }),
        });
        if (!res.ok) {
          var e = await res.json();
          return alert('\u30a8\u30e9\u30fc: ' + (e.error || 'Unknown'));
        }
        this.showModal = false;
        this.loadPrompts();
      },

      async deletePrompt() {
        if (!this.editingFile) return;
        if (!confirm(this.editingFile + ' \u3092\u524a\u9664\u3057\u307e\u3059\u304b\uff1f')) return;
        await api.del('/api/prompts/' + encodeURIComponent(this.editingFile));
        this.showModal = false;
        this.loadPrompts();
      },

      promptLines(content) {
        return (content || '').split('\n').length;
      },

      promptPreview(content) {
        return (content || '').slice(0, 150);
      },
    };
  });
});
