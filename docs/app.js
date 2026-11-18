// Osprey Launcher product page: live window previews and the latest-release download links.
(() => {
  "use strict";

  const REPO = "TariqMK/Osprey-Launcher";
  const ASSET = { windows: /windows-x64\.exe$/i, macos: /macos-arm64\.zip$/i, linux: /linux-x64\.tar\.gz$/i };
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const STAR = '<svg class="star" viewBox="0 0 24 24"><path d="M12 2.8l2.8 5.7 6.3.9-4.6 4.4 1.1 6.3L12 17.1l-5.6 3 1.1-6.3L2.9 9.4l6.3-.9z"/></svg>';

  // ---------- sample data (made up) ----------
  const ITEMS = {
    Work: [
      { name: "Budget 2026.xlsx", kind: "File", star: true },
      { name: "Meeting notes.docx", kind: "File" },
      { name: "Field guide.pdf", kind: "File" },
      { name: "Projects", kind: "Folder", star: true },
      { name: "Invoices", kind: "Folder" },
      { name: "Reports", kind: "Folder" },
      { name: "example.com", kind: "Link", star: true },
      { name: "Calendar", kind: "App" },
      { name: "Timesheet.xlsx", kind: "File" },
      { name: "Contracts", kind: "Folder" },
    ],
    Studio: [
      { name: "Client brief.pdf", kind: "File" },
      { name: "Moodboard.png", kind: "File" },
      { name: "Studio files", kind: "Folder" },
      { name: "portfolio.example.com", kind: "Link" },
      { name: "Sketchbook", kind: "App" },
      { name: "Type specimens", kind: "Folder" },
    ],
    Home: [
      { name: "Passport scan.pdf", kind: "File" },
      { name: "Recipes", kind: "Folder" },
      { name: "Holiday 2025", kind: "Folder" },
      { name: "news.example.org", kind: "Link" },
      { name: "Music", kind: "App" },
    ],
  };

  const el = (id) => document.getElementById(id);
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");

  function icon(kind, name, dim) {
    const d = dim ? " dim" : "";
    if (kind === "Folder") return `<span class="ic ic-folder${d}"></span>`;
    if (kind === "App") return `<span class="ic ic-app${d}"></span>`;
    if (kind === "Link") return `<span class="ic ic-link${d}">${esc(name[0].toUpperCase())}</span>`;
    return `<span class="ic ic-doc${d}"></span>`;
  }

  function tile(item, n, opts = {}) {
    const meta = opts.missing
      ? `<div class="tile-meta missing"><span class="nf">Not found</span><span class="locate">Locate</span></div>`
      : `<div class="tile-meta">${esc(opts.where ? `${opts.where} · ${item.kind}` : item.kind)}</div>`;
    const star = STAR.replace('class="star"', `class="star${item.star ? "" : " off"}"`);
    return `<div class="tile" data-n="${n}">
      <div class="tile-top">${icon(item.kind, item.name, opts.missing)}
        <span class="marks">${star}${n <= 9 ? `<span class="key">${n}</span>` : ""}</span></div>
      <div class="tile-name">${esc(item.name)}</div>${meta}</div>`;
  }

  function tabsHtml(names, active, starred) {
    const star = starred ? `<span class="tab${active === "Starred" ? " on" : ""}">${STAR}Starred</span>` : "";
    return star + names.map((t) => `<span class="tab${t === active ? " on" : ""}">${t}</span>`).join("");
  }

  // ---------- fixed heights: each grid reserves room for its tallest state ----------
  // The previews change their content as they play. Without this, a grid with more rows
  // makes its window taller and pushes the rest of the page down.
  const fitters = [];
  function fixHeight(box, states) {
    const fit = () => {
      const current = box.innerHTML;
      box.style.minHeight = "";
      let max = 0;
      for (const html of states) {
        box.innerHTML = html;
        max = Math.max(max, box.offsetHeight);
      }
      box.innerHTML = current;
      box.style.minHeight = `${max}px`;
    };
    fitters.push(fit);
    fit();
  }
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => fitters.forEach((f) => f()), 150);
  });

  // ---------- a tiny scheduler that pauses while the tab is hidden ----------
  const loops = [];
  function loop(steps) {
    const state = { i: 0, wait: 0 };
    loops.push(() => {
      if (state.wait > 0) { state.wait--; return; }
      const [fn, ticks] = steps[state.i];
      fn();
      state.wait = ticks - 1;
      state.i = (state.i + 1) % steps.length;
    });
  }
  function start() {
    if (reduced) return;
    setInterval(() => { if (!document.hidden) loops.forEach((f) => f()); }, 400);
  }

  // ---------- hero: tabs and keys 1-9 ----------
  function hero() {
    const grid = el("hero-grid");
    const tabs = el("hero-tabs");
    const names = Object.keys(ITEMS);
    const status = el("hero-status");
    const mac = /Mac/.test(navigator.platform || navigator.userAgent);
    const hint = `Press 1–9 to open, ${mac ? "⌘K" : "Ctrl+K"} to search`;
    status.textContent = hint;

    const listFor = (tab) => tab === "Starred"
      ? names.flatMap((t) => ITEMS[t].filter((i) => i.star).map((i) => ({ ...i, where: t })))
      : ITEMS[tab];
    const gridHtml = (list) => list.slice(0, 10).map((it, i) => tile(it, i + 1, { where: it.where })).join("");

    function show(tab) {
      const list = listFor(tab);
      tabs.innerHTML = tabsHtml(names, tab, true);
      el("hero-title").textContent = tab;
      el("hero-count").textContent = `${list.length} items`;
      grid.innerHTML = gridHtml(list);
      return list;
    }

    let list = show("Work");
    fixHeight(grid, [...names, "Starred"].map((t) => gridHtml(listFor(t))));
    if (reduced) return;
    const press = (n) => () => {
      const t = grid.querySelector(`.tile[data-n="${n}"]`);
      if (!t) return;
      const key = t.querySelector(".key");
      key.classList.add("down");
      t.classList.add("hit");
      status.textContent = `Opened ${list[n - 1].name}`;
      setTimeout(() => key.classList.remove("down"), 180);
      setTimeout(() => t.classList.remove("hit"), 900);
    };
    const go = (tab) => () => { list = show(tab); status.textContent = hint; };
    loop([
      [press(1), 5], [press(4), 5], [press(7), 6],
      [go("Studio"), 4], [press(2), 5], [press(4), 6],
      [go("Starred"), 4], [press(3), 6],
      [go("Home"), 4], [press(1), 6],
      [go("Work"), 4],
    ]);
  }

  // ---------- search across tabs ----------
  function search() {
    const all = Object.entries(ITEMS).flatMap(([t, items]) => items.map((i) => ({ ...i, where: t })));
    const text = el("search-text");
    const grid = el("search-grid");
    const count = el("search-count");

    const QUERIES = ["port", "plan", "notes"];
    const hitsFor = (q) => (q ? all.filter((i) => i.name.toLowerCase().includes(q.toLowerCase())) : []);
    const gridHtml = (hits) => hits.slice(0, 5).map((it, i) => tile(it, i + 1, { where: it.where })).join("");

    function render(q) {
      text.textContent = q;
      const hits = hitsFor(q);
      count.textContent = q ? `${hits.length} item${hits.length === 1 ? "" : "s"}` : "";
      grid.innerHTML = gridHtml(hits);
    }

    render("port");
    fixHeight(grid, QUERIES.flatMap((q) => [...q].map((_c, i) => gridHtml(hitsFor(q.slice(0, i + 1))))));
    if (reduced) return;
    const steps = [];
    for (const q of QUERIES) {
      for (let i = 1; i <= q.length; i++) steps.push([() => render(q.slice(0, i)), 1]);
      steps.push([() => {}, 7]);
      steps.push([() => render(""), 2]);
    }
    loop(steps);
  }

  // ---------- drag and drop ----------
  function drop() {
    const grid = el("drop-grid");
    const overlay = el("drop-overlay");
    const chip = el("drag-chip");
    const base = ITEMS.Studio.slice(0, 3);
    const added = { name: "Quarterly plan.pdf", kind: "File" };
    const gridHtml = (items) => items.map((it, i) => tile(it, i + 1)).join("");
    const render = (items) => { grid.innerHTML = gridHtml(items); };

    render(reduced ? [...base, added] : base);
    fixHeight(grid, [gridHtml(base), gridHtml([...base, added])]);
    if (reduced) return;
    loop([
      [() => { render(base); chip.classList.remove("inside"); chip.classList.add("show"); }, 2],
      [() => chip.classList.add("inside"), 2],
      [() => overlay.classList.add("on"), 3],
      [() => {
        overlay.classList.remove("on");
        chip.classList.remove("show");
        render([...base, added]);
        const t = grid.lastElementChild;
        t.classList.add("enter");
        requestAnimationFrame(() => requestAnimationFrame(() => t.classList.remove("enter")));
      }, 2],
      [() => grid.lastElementChild.classList.add("hit"), 2],
      [() => grid.lastElementChild.classList.remove("hit"), 6],
      [() => chip.classList.remove("inside"), 2],
    ]);
  }

  // ---------- starred and not found ----------
  function stars() {
    const grid = el("star-grid");
    const tabs = el("star-tabs");
    const items = [
      { name: "Client brief.pdf", kind: "File" },
      { name: "Logo draft.png", kind: "File" },
      { name: "Studio files", kind: "Folder" },
    ];
    let missing = false;
    let starred = false;

    const gridHtml = (s, m) => items.map((it, i) => tile({ ...it, star: s && i === 0 }, i + 1, { missing: m && i === 1 })).join("");

    function render() {
      tabs.innerHTML = tabsHtml(["Work", "Studio", "Home"], "Studio", starred);
      grid.innerHTML = gridHtml(starred, missing);
    }

    starred = true;
    missing = true;
    render();
    fixHeight(grid, [gridHtml(false, false), gridHtml(true, true)]);
    if (reduced) return;
    const set = (s, m) => () => { starred = s; missing = m; render(); };
    loop([
      [set(false, false), 5],
      [() => grid.firstElementChild.classList.add("hit"), 2],
      [() => { set(true, false)(); grid.firstElementChild.classList.add("hit"); }, 2],
      [() => grid.firstElementChild.classList.remove("hit"), 4],
      [set(true, true), 6],
      [() => grid.querySelector(".locate").classList.add("hit"), 3],
      [() => { set(true, false)(); grid.children[1].classList.add("hit"); }, 3],
      [() => grid.children[1].classList.remove("hit"), 5],
    ]);
  }

  // ---------- downloads ----------
  function detectOs() {
    const ua = navigator.userAgent;
    if (/Android|iPhone|iPad|iPod/i.test(ua)) return null;
    if (/Windows/i.test(ua)) return "windows";
    if (/Mac/i.test(ua)) return "macos";
    if (/Linux|X11/i.test(ua)) return "linux";
    return null;
  }

  function downloads() {
    const os = detectOs();
    const label = { windows: "Windows", macos: "macOS", linux: "Linux" };
    const hero = el("hero-download");
    if (os) {
      hero.textContent = `Download for ${label[os]}`;
      document.querySelector(`.card[data-os="${os}"]`).classList.add("mine");
    }
    fetch(`https://api.github.com/repos/${REPO}/releases/latest`, { headers: { Accept: "application/vnd.github+json" } })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((rel) => {
        for (const asset of rel.assets || []) {
          for (const [key, pattern] of Object.entries(ASSET)) {
            if (!pattern.test(asset.name)) continue;
            const card = document.querySelector(`.card[data-os="${key}"]`);
            card.href = asset.browser_download_url;
            card.querySelector(".size").textContent = `· ${(asset.size / 1048576).toFixed(1)} MB`;
            if (key === os) hero.href = asset.browser_download_url;
          }
        }
        const date = new Date(rel.published_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
        el("dl-version").textContent = `${rel.tag_name} · ${date}`;
        el("hero-meta").textContent = `${rel.tag_name} · Free · GPL-3.0 · Works offline · No tracking`;
        el("hero-version").textContent = rel.tag_name;
      })
      .catch(() => { /* No release yet, offline or rate-limited: links already point to the Releases page. */ });
  }

  hero();
  search();
  drop();
  stars();
  downloads();
  start();
})();
