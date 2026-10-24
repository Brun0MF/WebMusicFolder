// Small UI helpers; htmx and Alpine are loaded separately.
document.addEventListener("alpine:init", () => {
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    });
    if (response.status === 401) {
      window.location.href = "/login";
      throw new Error("Session expired");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
    }
    return data;
  }

  Alpine.data("submitForm", () => ({
    links: "",
    subfolder: "",
    folders: [],
    result: null,
    busy: false,
    error: "",
    message: "",
    // video_id -> 'skip' | 'redownload' for videos the app already has
    choice: {},

    get existing() {
      return this.result ? this.result.duplicates.filter((d) => d.kind === "exists") : [];
    },
    get inQueue() {
      return this.result ? this.result.duplicates.filter((d) => d.kind === "queued") : [];
    },
    get toQueue() {
      if (!this.result) return [];
      const dup = new Map(this.result.duplicates.map((d) => [d.video_id, d.kind]));
      return this.result.items
        .filter((i) => {
          const kind = dup.get(i.video_id);
          if (kind === "queued") return false;
          return kind !== "exists" || this.choice[i.video_id] === "redownload";
        })
        .map((i) => ({ ...i, overwrite: dup.get(i.video_id) === "exists" }));
    },
    // Appends a link from the search box once; the usual preview step does the rest.
    addLink(url) {
      const lines = this.links.split("\n").map((l) => l.trim());
      if (!lines.includes(url)) this.links = (this.links.trim() ? this.links.replace(/\s*$/, "\n") : "") + url;
    },
    setAll(value) {
      this.existing.forEach((d) => { this.choice[d.video_id] = value; });
    },

    async loadFolders() {
      try {
        this.folders = (await api("/api/folders")).folders;
      } catch (_) {
        this.folders = [];
      }
    },

    async preview() {
      this.busy = true;
      this.error = "";
      this.message = "";
      this.result = null;
      try {
        const result = await api("/api/submit/preview", {
          method: "POST",
          body: JSON.stringify({ links: this.links, subfolder: this.subfolder }),
        });
        // Known videos are skipped unless the user picks redownload.
        this.choice = {};
        result.duplicates.filter((d) => d.kind === "exists")
          .forEach((d) => { this.choice[d.video_id] = "skip"; });
        this.result = result;
      } catch (err) {
        this.error = err.message;
      } finally {
        this.busy = false;
      }
    },

    async confirm() {
      this.busy = true;
      this.error = "";
      try {
        const skipped = this.result.total - this.toQueue.length;
        const done = this.toQueue.length === 0
          ? { queued: 0, ignored: 0 }
          : await api("/api/submit/confirm", {
              method: "POST",
              body: JSON.stringify({ subfolder: this.result.subfolder, items: this.toQueue }),
            });
        this.message = `${done.queued} item(s) queued` +
          (skipped || done.ignored ? `, ${skipped + done.ignored} skipped` : "");
        this.result = null;
        this.links = "";
        this.loadFolders();
      } catch (err) {
        this.error = err.message;
      } finally {
        this.busy = false;
      }
    },
  }));

  Alpine.data("searchBox", () => ({
    q: "",
    results: [],
    added: new Set(),
    busy: false,
    done: false,
    error: "",

    clock(seconds) { return formatClock(seconds); },
    async run() {
      this.busy = true;
      this.error = "";
      this.done = false;
      try {
        this.results = (await api("/api/search", { method: "POST", body: JSON.stringify({ q: this.q }) })).results;
        this.added = new Set();
        this.done = true;
      } catch (err) {
        this.results = [];
        this.error = err.message;
      } finally {
        this.busy = false;
      }
    },
    add(result) {
      window.dispatchEvent(new CustomEvent("add-link", { detail: result.url }));
      this.added = new Set(this.added).add(result.video_id);
    },
  }));

  const GROUP = { downloading: 0, queued: 1, failed: 2, done: 3 };

  function formatSpeed(bps) {
    if (!bps) return "";
    return bps >= 1048576 ? `${(bps / 1048576).toFixed(1)} MB/s` : `${Math.round(bps / 1024)} kB/s`;
  }

  function formatClock(seconds) {
    const total = Math.max(0, Math.round(seconds || 0));
    const m = Math.floor(total / 60);
    return `${m}:${String(total % 60).padStart(2, "0")}`;
  }

  function formatSize(bytes) {
    if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(bytes / 1024))} kB`;
  }

  // Opens /events and calls the handlers; reconnects (and gets a new snapshot) on loss.
  function openEvents(handlers) {
    let source = null;
    let timer = null;
    let closed = false;
    const connect = () => {
      source = new EventSource("/events");
      for (const [name, fn] of Object.entries(handlers)) {
        source.addEventListener(name, (e) => fn(JSON.parse(e.data)));
      }
      source.onopen = () => handlers.connection && handlers.connection(true);
      source.onerror = () => {
        handlers.connection && handlers.connection(false);
        if (source.readyState === EventSource.CLOSED && !closed) {
          timer = setTimeout(connect, 3000);
        }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); source.close(); };
  }

  const COOKIE_CODES = ["private", "age_restricted", "login"];

  // Item errors are stored as "<code>: <readable message>[: <raw yt-dlp text>]".
  function errorParts(item) {
    const text = item.error || "";
    const m = text.match(/^([a-z_]+): ([\s\S]*)$/);
    if (!m) return { code: "", headline: text, raw: "", retry: "" };
    const retry = (m[2].match(/\s*\(retry \d+ of \d+\)$/) || [""])[0].trim();
    const body = retry ? m[2].slice(0, m[2].length - retry.length).trim() : m[2];
    const cut = body.indexOf(": ");
    return {
      code: m[1],
      headline: cut === -1 ? body : body.slice(0, cut),
      raw: cut === -1 ? "" : body.slice(cut + 2),
      retry,
    };
  }

  Alpine.data("themeToggle", () => ({
    light: document.documentElement.dataset.theme === "light",
    flip() {
      this.light = !this.light;
      const name = this.light ? "light" : "dark";
      document.documentElement.dataset.theme = name;
      try { localStorage.setItem("wmf-theme", name); } catch (e) { /* private mode */ }
    },
  }));

  Alpine.data("queueList", () => ({
    toasts: [],
    items: [],
    progress: {},
    paused: null,
    connected: false,
    error: "",
    stop: null,

    start() {
      this.stop = openEvents({
        connection: (ok) => { this.connected = ok; },
        snapshot: (d) => {
          this.items = d.items;
          this.progress = {};
          d.progress.forEach((p) => { this.progress[p.id] = p; });
          this.paused = d.paused;
        },
        item: (item) => {
          const i = this.items.findIndex((x) => x.id === item.id);
          const previous = i === -1 ? null : this.items[i];
          if (i === -1) this.items.push(item); else this.items[i] = item;
          if (item.status === "failed" && (!previous || previous.status !== "failed")) {
            this.toast(item);
          }
          if (item.status !== "downloading") delete this.progress[item.id];
        },
        progress: (p) => { this.progress = { ...this.progress, [p.id]: { ...this.progress[p.id], ...p } }; },
        removed: (d) => {
          this.items = this.items.filter((x) => x.id !== d.id);
          delete this.progress[d.id];
        },
        paused: (d) => { this.paused = d.reason; },
      });
    },
    destroy() { if (this.stop) this.stop(); },

    toast(item) {
      const id = `${item.id}-${Date.now()}`;
      const text = `${item.title || item.video_id}: ${this.parts(item).headline || "Failed"}`;
      this.toasts.push({ id, text });
      setTimeout(() => { this.toasts = this.toasts.filter((t) => t.id !== id); }, 8000);
    },
    parts(item) { return errorParts(item); },
    needsCookies(item) { return COOKIE_CODES.includes(errorParts(item).code); },
    async bulkAct(action) {
      this.error = "";
      try {
        await api(`/api/queue/${action}`, { method: "POST" });
      } catch (err) {
        this.error = err.message;
      }
    },
    async cancelAll() {
      if (!window.confirm(`Cancel ${this.remaining} queued or running download(s)?`)) return;
      await this.bulkAct("cancel_all");
    },
    async retryAll() {
      this.error = "";
      try {
        await api("/api/queue/retry_failed", { method: "POST" });
      } catch (err) {
        this.error = err.message;
      }
    },
    get sorted() {
      const rank = (x) => GROUP[x.status] ?? 9;
      return [...this.items].sort((a, b) => {
        if (rank(a) !== rank(b)) return rank(a) - rank(b);
        // Newest finished first; queue order otherwise.
        if (a.status === "done") return (b.finished_at || "").localeCompare(a.finished_at || "");
        return 0;
      });
    },
    count(status) { return this.items.filter((x) => x.status === status).length; },
    get remaining() { return this.count("queued") + this.count("downloading"); },
    get summary() {
      const done = this.count("done");
      const failed = this.count("failed");
      return `${done} of ${this.items.length} done, ${this.remaining} remaining` +
        (failed ? `, ${failed} failed` : "");
    },
    // No known percentage yet, or post processing: show a moving stripe instead of an empty bar.
    indeterminate(item) {
      const p = this.progress[item.id] || {};
      return Boolean(p.stage) || p.pct == null;
    },
    pct(item) { return Math.round((this.progress[item.id] || {}).pct || 0); },
    detail(item) {
      if (item.status === "queued") {
        const p = errorParts(item);
        return item.error ? `${p.headline} ${p.retry}`.trim() : "Waiting";
      }
      if (item.status === "failed") return errorParts(item).headline || "Failed";
      if (item.status === "done") return item.subfolder ? `Saved in ${item.subfolder}` : "Saved";
      const p = this.progress[item.id] || {};
      if (p.stage) return `${p.stage}...`;
      return [formatSpeed(p.speed), p.eta != null ? `ETA ${formatClock(p.eta)}` : ""]
        .filter(Boolean).join(", ");
    },
    async act(item, action) {
      this.error = "";
      try {
        await api(`/api/queue/${item.id}/${action}`, { method: "POST" });
      } catch (err) {
        this.error = err.message;
      }
    },
  }));

  const LOG_KEEP = 1000;

  Alpine.data("logsPage", () => ({
    entries: [],
    filter: "",
    follow: true,
    connected: false,
    error: "",
    stop: null,

    init() {
      // Subscribe first so lines arriving while the history loads are not lost.
      this.stop = openEvents({
        connection: (ok) => {
          this.connected = ok;
          if (ok) this.load();
        },
        log: (entry) => this.push([entry]),
      });
    },
    destroy() { if (this.stop) this.stop(); },

    push(batch) {
      const seen = new Set(this.entries.map((e) => e.seq));
      const fresh = batch.filter((e) => !seen.has(e.seq));
      if (!fresh.length) return;
      this.entries = this.entries.concat(fresh).sort((a, b) => a.seq - b.seq).slice(-LOG_KEEP);
      if (this.follow) {
        this.$nextTick(() => {
          const box = this.$refs.box;
          if (box) box.scrollTop = box.scrollHeight;
        });
      }
    },
    async load() {
      try {
        this.push((await api("/api/logs")).entries);
        this.error = "";
      } catch (err) {
        this.error = err.message;
      }
    },
    get items() {
      const seen = new Map();
      this.entries.forEach((e) => { if (e.item) seen.set(e.item, e.title || e.item); });
      return [...seen].map(([id, title]) => ({ id, title }));
    },
    get visible() {
      return this.filter ? this.entries.filter((e) => e.item === this.filter) : this.entries;
    },
    clear() { this.entries = []; },
    time(entry) { return entry.ts.slice(11, 19); },
    level(entry) {
      if (entry.line.startsWith("ERROR")) return "log-error";
      if (entry.line.startsWith("WARNING")) return "log-warn";
      return "";
    },
  }));

  Alpine.data("settingsPage", () => ({
    ytdlp: { version: "", busy: false, result: null, error: "" },
    cookies: { loaded: false, saved_at: null, browser: null, text: "", busy: false, error: "", message: "" },
    options: { sponsorblock: false, replaygain: false, busy: false, error: "" },
    config: { music_dir: "", default_music_dir: "", quality: "v5", concurrency: 1, qualities: [], max_concurrency: 4, data_dir: "", busy: false, error: "", message: "" },

    pw: { current: "", next: "", again: "", busy: false, error: "", message: "" },
    async changePassword() {
      const p = this.pw;
      p.error = "";
      p.message = "";
      if (p.next !== p.again) { p.error = "The new passwords do not match"; return; }
      p.busy = true;
      try {
        await api("/api/account/password", {
          method: "POST",
          body: JSON.stringify({ current: p.current, new: p.next }),
        });
        p.current = p.next = p.again = "";
        p.message = "Password changed. Other devices were signed out.";
      } catch (err) {
        p.error = err.message;
      } finally {
        p.busy = false;
      }
    },

    qualityLabel(q) {
      const names = {
        v0: "V0 (about 245 kbps, largest)",
        v2: "V2 (about 190 kbps)",
        v5: "V5 (about 130 kbps, smallest, recommended)",
        "320k": "320 kbps (constant)",
        "192k": "192 kbps (constant)",
        "128k": "128 kbps (constant)",
      };
      return names[q] || q;
    },
    // A select whose options appear after its value is set would show the first option; set it again once they exist.
    syncSelect(el, value, optionCount) {
      this.$nextTick(() => { if (optionCount) el.value = String(value); });
    },
    async loadConfig() {
      try {
        Object.assign(this.config, await api("/api/config"));
      } catch (err) {
        this.config.error = err.message;
      }
    },
    async saveConfig(body) {
      const c = this.config;
      c.busy = true;
      c.error = "";
      c.message = "";
      try {
        Object.assign(c, await api("/api/config", { method: "POST", body: JSON.stringify(body) }));
        c.message = "Saved";
      } catch (err) {
        c.error = err.message;
        await this.loadConfig();
      } finally {
        c.busy = false;
      }
    },

    init() {
      this.loadConfig();
      this.loadOptions();
      this.loadVersion();
      this.loadCookies();
    },

    async loadOptions() {
      try {
        Object.assign(this.options, await api("/api/settings"));
      } catch (err) {
        this.options.error = err.message;
      }
    },
    async saveOption(name) {
      const o = this.options;
      o.busy = true;
      o.error = "";
      try {
        Object.assign(o, await api("/api/settings", { method: "POST", body: JSON.stringify({ [name]: o[name] }) }));
      } catch (err) {
        o.error = err.message;
        // Show what the server really has.
        await this.loadOptions();
      } finally {
        o.busy = false;
      }
    },

    async loadVersion() {
      try {
        this.ytdlp.version = (await api("/api/ytdlp/version")).version;
      } catch (err) {
        this.ytdlp.error = err.message;
      }
    },
    async updateYtdlp() {
      const y = this.ytdlp;
      y.busy = true;
      y.error = "";
      y.result = null;
      try {
        y.result = await api("/api/ytdlp/update", { method: "POST" });
        y.version = y.result.new;
      } catch (err) {
        y.error = err.message;
      } finally {
        y.busy = false;
      }
    },
    get updateText() {
      const r = this.ytdlp.result;
      if (!r) return "";
      return r.changed ? `Updated from ${r.old} to ${r.new}.` : `Already on the latest version (${r.new}).`;
    },

    async loadCookies() {
      try {
        Object.assign(this.cookies, await api("/api/cookies"));
      } catch (err) {
        this.cookies.error = err.message;
      }
    },
    async saveCookies(text) {
      const c = this.cookies;
      c.busy = true;
      c.error = "";
      c.message = "";
      try {
        Object.assign(c, await api("/api/cookies", { method: "POST", body: JSON.stringify({ text }) }));
        // The pasted text is dropped as soon as it is stored.
        c.text = "";
        c.message = "Cookies saved.";
      } catch (err) {
        c.error = err.message;
      } finally {
        c.busy = false;
      }
    },
    async pickFile(event) {
      const file = event.target.files[0];
      event.target.value = "";
      if (!file) return;
      if (file.size > 512 * 1024) {
        this.cookies.error = "The file is too large to be a cookies.txt";
        return;
      }
      await this.saveCookies(await file.text());
    },
    async deleteCookies() {
      const c = this.cookies;
      c.busy = true;
      c.error = "";
      c.message = "";
      try {
        Object.assign(c, await api("/api/cookies", { method: "DELETE" }));
        c.message = "Cookies deleted.";
      } catch (err) {
        c.error = err.message;
      } finally {
        c.busy = false;
      }
    },
    get cookieSource() {
      if (this.cookies.loaded) return "cookies.txt";
      if (this.cookies.browser) return `Browser: ${this.cookies.browser.replace(":", ", profile ")}`;
      return "none";
    },
    savedAt() {
      return this.cookies.saved_at ? this.cookies.saved_at.replace("T", " ").replace("Z", " UTC") : "";
    },
  }));

  Alpine.data("libraryPage", () => ({
    folders: [],
    selected: new Set(),
    moveTarget: "",
    newFolder: "",
    folderBusy: false,
    folderError: "",
    bulkBusy: false,
    notice: "",
    entries: [],
    subfolders: [],
    total: 0,
    q: "",
    subfolder: "",
    source: "",
    loading: false,
    error: "",
    timer: null,
    stop: null,
    linking: "",
    linkText: "",
    linkError: "",
    linkBusy: false,
    deleting: "",

    async remove(entry) {
      if (!window.confirm(`Delete "${entry.title}" from disk? This cannot be undone.`)) return;
      this.deleting = entry.path;
      this.error = "";
      this.notice = "";
      try {
        await api("/api/library", {
          method: "DELETE",
          body: JSON.stringify({ path: entry.path }),
        });
        await this.load();
      } catch (err) {
        this.error = err.message;
      } finally {
        this.deleting = "";
      }
    },

    get allSelected() {
      return this.entries.length > 0 && this.entries.every((e) => this.selected.has(e.path));
    },
    toggle(path, on) {
      const next = new Set(this.selected);
      if (on) next.add(path); else next.delete(path);
      this.selected = next;
    },
    toggleAll(on) {
      this.selected = on ? new Set(this.entries.map((e) => e.path)) : new Set();
    },
    summary(verb, out) {
      const failed = out.failed.length;
      this.notice = `${verb} ${out.done} track(s)` + (failed ? `, ${failed} skipped: ${out.failed[0].reason}` : "");
    },
    async deleteSelected() {
      const n = this.selected.size;
      if (!window.confirm(`Delete ${n} track(s) from disk? This cannot be undone.`)) return;
      await this.bulk("/api/library/delete", { paths: [...this.selected] }, "Deleted");
    },
    async moveSelected() {
      const subfolder = this.moveTarget === "/" ? "" : this.moveTarget;
      await this.bulk("/api/library/move", { paths: [...this.selected], subfolder }, "Moved");
    },
    async bulk(url, body, verb) {
      this.bulkBusy = true;
      this.error = "";
      this.notice = "";
      try {
        const out = await api(url, { method: "POST", body: JSON.stringify(body) });
        this.summary(verb, out);
        this.selected = new Set();
        await this.load();
      } catch (err) {
        this.error = err.message;
      } finally {
        this.bulkBusy = false;
      }
    },
    async createFolder() {
      this.folderBusy = true;
      this.folderError = "";
      try {
        await api("/api/library/folders", { method: "POST", body: JSON.stringify({ name: this.newFolder.trim() }) });
        this.newFolder = "";
        await this.load();
      } catch (err) {
        this.folderError = err.message;
      } finally {
        this.folderBusy = false;
      }
    },
    async removeFolder(folder) {
      const msg = folder.count
        ? `Delete folder "${folder.name}" and its ${folder.count} track(s)? This cannot be undone.`
        : `Delete the empty folder "${folder.name}"?`;
      if (!window.confirm(msg)) return;
      this.folderError = "";
      try {
        await api("/api/library/folders", { method: "DELETE", body: JSON.stringify({ name: folder.name }) });
        if (this.subfolder === folder.name) this.subfolder = "";
        await this.load();
      } catch (err) {
        this.folderError = err.message;
      }
    },
    openLink(entry) {
      this.linking = entry.path;
      this.linkText = "";
      this.linkError = "";
    },
    async saveLink(entry) {
      this.linkBusy = true;
      this.linkError = "";
      try {
        await api("/api/library/link", {
          method: "POST",
          body: JSON.stringify({ path: entry.path, link: this.linkText.trim() }),
        });
        this.linking = "";
        await this.load();
      } catch (err) {
        this.linkError = err.message;
      } finally {
        this.linkBusy = false;
      }
    },

    init() {
      this.load();
      // Reload after a download finishes, but only while this page is open.
      this.stop = openEvents({
        item: (item) => { if (item.status === "done") this.later(1500); },
      });
    },
    destroy() { if (this.stop) this.stop(); },

    later(ms) {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.load(), ms);
    },
    async load() {
      this.loading = true;
      this.error = "";
      const params = new URLSearchParams();
      if (this.q.trim()) params.set("q", this.q.trim());
      if (this.subfolder !== "") params.set("subfolder", this.subfolder === "/" ? "" : this.subfolder);
      if (this.source) params.set("source", this.source);
      try {
        const data = await api(`/api/library?${params}`);
        this.entries = data.entries;
        this.folders = data.folders;
        this.subfolders = data.subfolders;
        // Drop selections that are no longer on screen.
        const shown = new Set(data.entries.map((e) => e.path));
        this.selected = new Set([...this.selected].filter((p) => shown.has(p)));
        this.total = data.total;
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },
    async rescan() {
      this.loading = true;
      try {
        await api("/api/library/rescan", { method: "POST" });
      } catch (err) {
        this.error = err.message;
      }
      await this.load();
    },
    // Artist and album, leaving out whichever is Unknown (downloads carry no album tag).
    subline(entry) {
      const parts = [entry.artist, entry.album].filter((v) => v && v !== "Unknown");
      return parts.length ? parts.join(" - ") : "Unknown artist";
    },
    youtubeUrl(entry) {
      // video ids are 11 characters of [A-Za-z0-9_-]; anything else gets no link.
      return /^[\w-]{11}$/.test(entry.video_id || "")
        ? `https://www.youtube.com/watch?v=${entry.video_id}` : "#";
    },
    coverUrl(entry) { return `/api/library/cover?path=${encodeURIComponent(entry.path)}`; },
    duration(entry) { return formatClock(entry.duration_s); },
    size(entry) { return formatSize(entry.size); },
    folderLabel(name) { return name === "" ? "(music root)" : name; },
  }));
});
