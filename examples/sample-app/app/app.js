// TaskBoard — a deliberately small app used as ASDR's test and manual fixture.
// State lives in localStorage so tests can start from a clean slate by
// clearing it; there is no server beyond static file hosting.
(function () {
  const KEY = "taskboard.v1";
  const $ = (id) => document.getElementById(id);
  const load = () => {
    try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
  };
  const fresh = () => ({ user: null, tasks: [], nextId: 1,
    categories: ["General", "Bugs"], membersCanDelete: false, filter: "all" });
  let s = load() || fresh();
  const save = () => localStorage.setItem(KEY, JSON.stringify(s));

  function show(view) {
    for (const id of ["signin", "board", "settings"]) $(id).hidden = id !== view;
    $("nav").hidden = !s.user;
    if (s.user) {
      $("whoami").textContent = `${s.user.name} · ${s.user.role === "admin" ? "Team admin" : "Team member"}`;
      $("nav-settings").hidden = s.user.role !== "admin";
    }
  }

  function route() {
    if (!s.user) return show("signin");
    if (location.hash === "#settings" && s.user.role === "admin") { renderSettings(); return show("settings"); }
    renderBoard(); show("board");
  }

  function renderBoard() {
    const sel = $("new-task-category");
    sel.innerHTML = s.categories.map((c) => `<option>${escape(c)}</option>`).join("");
    const canDelete = s.user.role === "admin" || s.membersCanDelete;
    const list = s.tasks.filter((t) => s.filter === "all" || (s.filter === "done" ? t.done : !t.done));
    $("tasks").innerHTML = list.map((t) => `
      <li data-id="${t.id}" class="${t.done ? "done" : ""}">
        <input type="checkbox" aria-label="Mark ${escape(t.title)} done" ${t.done ? "checked" : ""}>
        <span class="title">${escape(t.title)}</span>
        <span class="tag">${escape(t.category)}</span>
        ${canDelete ? `<button class="delete" aria-label="Delete ${escape(t.title)}">Delete</button>` : ""}
      </li>`).join("");
    const open = s.tasks.filter((t) => !t.done).length;
    $("counter").textContent = `${open} open · ${s.tasks.length - open} done`;
    $("empty").hidden = s.tasks.length > 0;
    document.querySelectorAll("[data-filter]").forEach((b) =>
      b.classList.toggle("active", b.dataset.filter === s.filter));
  }

  function renderSettings() {
    $("categories").innerHTML = s.categories.map((c) => `<li>${escape(c)}</li>`).join("");
    $("members-can-delete").checked = s.membersCanDelete;
  }

  function escape(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  $("signin-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("name").value.trim();
    $("signin-error").hidden = !!name;
    if (!name) return;
    s.user = { name, role: $("role").value }; save(); location.hash = "#board"; route();
  });
  $("sign-out").addEventListener("click", () => { s.user = null; save(); location.hash = ""; route(); });

  $("new-task-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const title = $("new-task").value.trim();
    if (!title) return;
    s.tasks.push({ id: s.nextId++, title, category: $("new-task-category").value, done: false });
    $("new-task").value = ""; save(); renderBoard();
  });
  $("tasks").addEventListener("change", (e) => {
    const li = e.target.closest("li"); if (!li) return;
    const t = s.tasks.find((x) => x.id === Number(li.dataset.id)); t.done = e.target.checked; save(); renderBoard();
  });
  $("tasks").addEventListener("click", (e) => {
    if (!e.target.classList.contains("delete")) return;
    const id = Number(e.target.closest("li").dataset.id);
    s.tasks = s.tasks.filter((t) => t.id !== id); save(); renderBoard();
  });
  document.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => {
    s.filter = b.dataset.filter; save(); renderBoard();
  }));
  $("export").addEventListener("click", () => {
    const rows = [["id", "title", "category", "done"], ...s.tasks.map((t) => [t.id, t.title, t.category, t.done])];
    const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: "tasks.csv" });
    document.body.appendChild(a); a.click(); a.remove();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key.toLowerCase() === "n" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)
        && !$("board").hidden) { e.preventDefault(); $("new-task").focus(); }
  });

  $("new-category-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("new-category").value.trim();
    if (!name || s.categories.includes(name)) return;
    s.categories.push(name); $("new-category").value = ""; save(); renderSettings(); flash();
  });
  $("members-can-delete").addEventListener("change", (e) => { s.membersCanDelete = e.target.checked; save(); flash(); });
  function flash() { $("settings-saved").hidden = false; setTimeout(() => ($("settings-saved").hidden = true), 1500); }

  window.addEventListener("hashchange", route);
  route();
})();
