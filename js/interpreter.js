(function () {
  const app = document.getElementById("app");

  const BASE = normalizeBase(window.SITE_BASE || "/");
  const OWNER = window.REPO_OWNER;
  const REPO  = window.REPO_NAME;
  const BR    = window.REPO_BRANCH || "main";
  const CLASSES = Array.isArray(window.CLASSES) ? window.CLASSES : [];

  // Tweak this if you want bigger or smaller PDF text later
  const PDF_ZOOM = "100"; // percent. Alternatives that often work: "page-width", "175"

  boot().catch(err => {
    app.innerHTML = card(`<h2>Load error</h2><p class="muted">${escapeHtml(String(err))}</p>`);
  });

  async function boot() {
    const { cls, id } = parseRoute();
    if (!cls || !id) {
      app.innerHTML = card(`<h2>Missing route</h2>
        <p class="muted">Open with <code>${BASE}interpreter.html?class=DE&id=1.1.9%20Soldering%20Desoldering</code>
        or use a pretty URL like <code>${BASE}DE/1.1.9%20Soldering%20Desoldering</code>.</p>`);
      return;
    }

    const jsonUrl = buildJsonUrl(cls, id);
    const page = await fetchJson(jsonUrl);
    render(page, { cls, id });
  }

  // Supports ?class=DE&id=... and pretty URLs /eng-portfolio/DE/<id>
  function parseRoute() {
    const sp = new URLSearchParams(location.search);
    const clsQ = sp.get("class");
    const idQ  = sp.get("id");
    if (clsQ && idQ) return { cls: decodeURIComponent(clsQ), id: decodeURIComponent(idQ) };

    let path = decodeURIComponent(location.pathname);
    if (BASE !== "/" && path.startsWith(BASE)) path = path.slice(BASE.length);
    const parts = path.replace(/^\/+|\/+$/g, "").split("/");
    if (parts.length >= 2) {
      const cls = parts[0];
      if (CLASSES.length && !CLASSES.includes(cls)) return { cls: null, id: null };
      const id = parts.slice(1).join("/");
      return { cls, id };
    }
    return { cls: null, id: null };
  }

  // Pull JSON from pages/{CLASS}/{ID}.json in your repo
  function buildJsonUrl(cls, id) {
    if (!OWNER || !REPO) throw new Error("Missing REPO_OWNER or REPO_NAME in site.config.js");
    const path = ["pages", cls, `${id}.json`]
      .map(seg => seg.split("/").map(encodeURIComponent).join("/")).join("/");
    return `https://raw.githubusercontent.com/${encodeURIComponent(OWNER)}/${encodeURIComponent(REPO)}/${encodeURIComponent(BR)}/${path}`;
  }

  async function fetchJson(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`Page JSON not found at ${url}`);
    return r.json();
  }

  function render(page, ctx) {
    // helpers scoped to render
    function stripExt(s) { return String(s).replace(/\.[^.]+$/, ""); }
    function tpl(str, vars) {
      return String(str).replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : `{${k}}`));
    }

    // derive identifiers from ctx and URL
    const fromCtx   = ctx && ctx.id ? String(ctx.id) : "";
    const pathClean = decodeURIComponent(location.pathname.replace(/\/+$/, ""));
    const urlTail   = pathClean.split("/").pop() || "";
    const idStr     = fromCtx || urlTail;

    const fileBase  = stripExt((idStr.split("/").pop() || ""));
    const parentDir = decodeURIComponent(pathClean.split("/").slice(-2, -1)[0] || "");

    // fields from page JSON
    const rawTitle = page.title || page.name || ctx.id || fileBase;
    const date     = page.date || "";
    const type     = page.type || "";
    const brief    = Array.isArray(page.brief) ? page.brief : [];
    const elements = Array.isArray(page.elements) ? page.elements : [];

    // allow {file}, {class}, {id} in titles
    const title = tpl(rawTitle, { file: fileBase, class: parentDir, id: idStr });

    // set browser tab title
    document.title = `Team 5840C | VRC · ${title}`;

    // chips
    const chips = [
      ctx.cls ? `<span class="chip chip-class">${escapeHtml(ctx.cls)}</span>` : "",
      type ? `<span class="chip chip-type">${escapeHtml(type)}</span>` : ""
    ].join("");

    // header
    const header = `
      <header class="page-header">
        <h1 class="page-title">${escapeHtml(title)}</h1>
        <div class="page-tags">${chips}</div>
        ${date ? `<div class="page-date">${escapeHtml(date)}</div>` : ""}
      </header>
    `;

    // abstract
    const abstractHtml = brief.length
      ? `<section class="abstract element">
          <h2 class="element-title">Abstract</h2>
          <div class="card"><ul class="brief">${brief.map(li => `<li>${escapeHtml(li)}</li>`).join("")}</ul></div>
        </section>`
      : "";

    // elements
    const elementsHtml = renderElements(elements, ctx, page);

    // mount
    app.innerHTML = header + abstractHtml + elementsHtml;
    // hydrate any dynamic pieces (code blocks, etc.)
    hydrateCodeBlocks(app);
    wireCodeActions(app);
  }

  function renderElements(elements, ctx, page) {
    if (!elements.length) return "";
    return elements.map((el, i) => {
      const t = normalizeType(el.type);
      const renderer = RENDERERS[t] || renderUnknown;
      return renderer(el, ctx, i, page);
    }).join("");
  }

  const RENDERERS = {
    synopsis: (el) => {
      const text = el.content || el.text || "";
      const title = el.title || "Synopsis";
      return section(title, `<div class="card">${richText(text)}</div>`);
    },
    designbrief: (el) => {
      if (Array.isArray(el.items)) {
        const blocks = el.items.map((txt) =>
          `<div class="card" style="margin-top:10px">${richText(txt)}</div>`).join("");
        return section(el.title || "Design Brief", blocks);
      }
      return section(el.title || "Design Brief", `<div class="card">${richText(el.content || "")}</div>`);
    },
    notes: (el) => section(el.title || el.label || "Notes", `<div class="card">${richText(el.content || "")}</div>`),

    pdf: (el, ctx, _i, page) => {
      const items = normalizeItems(el);
      const content = items.map(it => {
        const src = makeSrc(it.src, page, ctx);
        const label = escapeHtml(it.label || "PDF");
        const embedUrl = `${src}#zoom=${encodeURIComponent(PDF_ZOOM)}`;
        const iframe = `<iframe class="pdf-frame" src="${embedUrl}"></iframe>`;
        const actions = `
          <div class="media-actions">
            <a class="btn" href="${embedUrl}" target="_blank" rel="noopener">Open in new tab</a>
            <a class="btn" href="${src}" download>Download</a>
          </div>`;
        return `<figure class="media">
                  <div class="media-center">${iframe}</div>
                  <figcaption class="media-caption">${label}</figcaption>
                  ${actions}
                </figure>`;
      }).join("");
      return section(el.label || "PDF", content);
    },

    video: (el, ctx, _i, page) => {
      const items = normalizeItems(el);
      const content = items.map(it => {
        const src = makeSrc(it.src, page, ctx);
        const embed = toVideoEmbed(src);
        const label = escapeHtml(it.label || "Video");
        return `<figure class="media">
                  <div class="media-center">${embed}</div>
                  <figcaption class="media-caption">${label}</figcaption>
                </figure>`;
      }).join("");
      return section(el.label || "Video", content);
    },

    // Script/code viewer with copy + download
    script: (el, ctx, i, page) => {
      const items = normalizeItems(el);
      const content = items.map((it, k) => {
        const src = it.code ? null : makeSrc(it.src, page, ctx);
        const label = escapeHtml(it.label || it.language || "Script");
        const lang  = escapeHtml(it.language || guessLang(it.src || ""));
        const codeId = `code-${i}-${k}-${Math.random().toString(36).slice(2,8)}`;
        const preAttrs = [
          `id="${codeId}"`,
          `class="code-window"`,
          lang ? `data-lang="${lang}"` : "",
          src ? `data-src="${src}"` : "",
        ].filter(Boolean).join(" ");
        const body = it.code
          ? `<pre ${preAttrs}>${escapeHtml(String(it.code))}</pre>`
          : `<pre ${preAttrs}>Loading script…</pre>`;
        const actions = `
          <div class="media-actions">
            <button class="btn btn-copy-code" data-target="${codeId}">Copy</button>
            ${src ? `<a class="btn" href="${src}" download>Download</a>` : ""}
          </div>`;
        return `<figure class="media">
                  <figcaption class="media-caption">${label}</figcaption>
                  ${body}
                  ${actions}
                </figure>`;
      }).join("");
      return section(el.label || "Script", content);
    },

    image: (el, ctx, _i, page) => {
      const items = normalizeItems(el);
      let describedCount = 0; // alternate only across described images
      const content = items.map((it) => {
        const src = makeSrc(it.src, page, ctx);
        const label = escapeHtml(it.label || "Image");
        const alt = escapeHtml(it.alt || it.label || page.title || "");
        const desc = it.description ? String(it.description) : "";

        if (desc) {
          const alignLeft = (describedCount % 2) === 0; // alternate L/R
          describedCount++;
          const alignClass = alignLeft ? "align-left" : "align-right";
          const img = `<img class="image-frame" src="${src}" alt="${alt}" loading="lazy">`;
          const text = `<div class="image-desc">${richText(desc)}</div>`;
          return `<figure class="media media-described ${alignClass}">
                    <figcaption class="media-caption">${label}</figcaption>
                    <div class="media-wrap">${img}${text}</div>
                  </figure>`;
        }

        // no description: render as before
        const img = `<img class="image-frame" src="${src}" alt="${alt}" loading="lazy">`;
        return `<figure class="media">
                  <figcaption class="media-caption">${label}</figcaption>
                  <div class="media-center">${img}</div>
                </figure>`;
      }).join("");
      return section(el.label || "Image", content);
    },
    images: (el, ctx, i, page) => RENDERERS.image(el, ctx, i, page)
  };

  function section(title, innerHtml) {
    return `<section class="element">
      <h2 class="element-title">${escapeHtml(title)}</h2>
      ${innerHtml}
    </section>`;
  }

  // ---------- helpers ----------
  function filenameStem(id) {
    const last = String(id || "").split("/").pop() || "";
    return last.replace(/\.[^.]+$/, "");
  }
  function normalizeItems(el) {
    if (Array.isArray(el.items)) return el.items;
    if (el.src) return [{ src: el.src, label: el.label }];
    return [];
  }
  function guessLang(p) {
    const s = String(p).toLowerCase();
    if (s.endsWith('.py')) return 'python';
    if (s.endsWith('.js') || s.endsWith('.mjs') || s.endsWith('.cjs')) return 'javascript';
    if (s.endsWith('.ts')) return 'typescript';
    if (s.endsWith('.cpp') || s.endsWith('.cc') || s.endsWith('.cxx')) return 'cpp';
    if (s.endsWith('.c')) return 'c';
    if (s.endsWith('.java')) return 'java';
    if (s.endsWith('.json')) return 'json';
    if (s.endsWith('.md')) return 'markdown';
    if (s.endsWith('.html')) return 'html';
    if (s.endsWith('.css')) return 'css';
    return '';
  }
  function normalizeType(t) { return String(t || "").toLowerCase().replace(/\s+/g, ""); }
  function isHttp(url) { return /^https?:\/\//i.test(url || ""); }
  function expandTemplatePath(p, page, ctx) {
    const idStr = String(ctx.id || "");
    const file  = filenameStem(idStr); // helper already in this file
    // Allow {file}, {class}, {id} inside title before using {title} in paths
    const templatedTitle = String(page.title || idStr)
      .replace(/\{file\}/g, file)
      .replace(/\{class\}/g, ctx.cls || "")
      .replace(/\{id\}/g, idStr);

    return String(p || "")
      .replace(/\{title\}/g, templatedTitle)
      .replace(/\{class\}/g, ctx.cls || "")
      .replace(/\{type\}/g, page.type || "")
      .replace(/\{id\}/g, idStr)
      .replace(/\{file\}/g, file);
  }
  function encodeLocalPath(p) { return String(p || "").split("/").map(seg => seg === "" ? "" : encodeURIComponent(seg)).join("/"); }
  function makeSrc(p, page, ctx) {
    const expanded = expandTemplatePath(p, page, ctx).replace(/^\/+/, "");
    if (isHttp(expanded)) return expanded;
    return BASE + encodeLocalPath(expanded);
  }
  async function hydrateCodeBlocks(root) {
    const list = Array.from(root.querySelectorAll('pre.code-window[data-src]'));
    await Promise.all(list.map(async (pre) => {
      const url = pre.getAttribute('data-src');
      try {
        const r = await fetch(url, { cache: 'no-store' });
        pre.textContent = r.ok ? (await r.text()) : `Failed to load: ${url}`;
      } catch (e) {
        pre.textContent = `Error loading: ${url}`;
      }
    }));
  }
  function wireCodeActions(root) {
    root.addEventListener('click', async (ev) => {
      const btn = ev.target.closest('.btn-copy-code');
      if (!btn) return;
      const id = btn.getAttribute('data-target');
      const pre = id && root.querySelector(`#${CSS.escape(id)}`);
      if (!pre) return;
      const text = pre.textContent || '';
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = 'Copied!';
      } catch {
        try {
          const ta = document.createElement('textarea');
          ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
          btn.textContent = 'Copied!';
        } catch {}
      }
      setTimeout(() => { btn.textContent = 'Copy'; }, 1200);
    });
  }
  function toVideoEmbed(src) {
    const url = String(src || "");
    if (/youtu\.be|youtube\.com/.test(url)) {
      const idMatch = url.match(/(?:v=|\/)([0-9A-Za-z_-]{11})/);
      const id = idMatch ? idMatch[1] : null;
      const embed = id ? "https://www.youtube.com/embed/" + id : url;
      return `<iframe class="video-frame" src="${embed}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`;
    }
    if (/\.(mp4|webm|ogg)(\?|$)/i.test(url)) {
      return `<video class="video-frame" controls src="${url}"></video>`;
    }
    return `<iframe class="video-frame" src="${url}"></iframe>`;
  }
  function card(inner) { return `<div class="card" style="padding:14px;border-radius:14px">${inner}</div>`; }
  function normalizeBase(b) { return b && !b.endsWith("/") ? b + "/" : (b || "/"); }
  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;","&gt;":"&gt;",'"':"&quot;","'":"&#39;" }[c])); }
  function richText(s) {
    const esc = escapeHtml(String(s));
    const linked = esc.replace(/(https?:\/\/[^\s)]+)/g, '<a href="$1" class="btn">$1</a>');
    return linked.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }
})();
