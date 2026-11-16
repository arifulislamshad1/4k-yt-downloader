(() => {
  "use strict";
  if (window.top !== window) return;
  if (window.__ytdlAnyLoaded) return;
  window.__ytdlAnyLoaded = true;

  const HOST_ID = "ytdl-any-host";
  const MIN_W = 240, MIN_H = 135;
  const PLAYER_IFRAME = /youtube\.com\/embed|youtu\.be|vimeo\.com|dailymotion|facebook\.com\/plugins\/video|player|embed|video|stream/i;
  const PERMALINK = /(\/reels?\/[\w-]+|\/videos?\/|\/watch\/?\?|\/watch\?|\/shorts\/|\/status\/\d+|\/p\/[\w-]+|\/tv\/[\w-]+|\/posts\/|\/permalink|\/clip\/|[?&]v=\w)/i;
  const SINGLE_PAGE = /(\/(reels?|shorts|videos?|tv|clips?)\/[\w-]+|\/watch|\/status\/\d+|\/p\/[\w-]+|[?&]v=\w)/i;
  const STANDARD = [["4320", "Best available"], ["1080", "1080p"], ["720", "720p"], ["480", "480p"]];

  const targets = new Map();
  let hostEl = null, layer = null, dismissed = false;

  function ensureLayer() {
    if (hostEl && hostEl.isConnected) return;
    hostEl = document.createElement("div");
    hostEl.id = HOST_ID;
    hostEl.style.cssText = "all:initial;position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647;";
    const root = hostEl.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        *{box-sizing:border-box;font:500 12px Roboto,Arial,sans-serif}
        .pill{position:fixed;display:none}
        .btn{display:flex;align-items:center;gap:6px;height:30px;padding:0 14px;border:0;border-radius:15px;
          background:#cc0000;color:#fff;cursor:pointer;box-shadow:0 1px 6px rgba(0,0,0,.5)}
        .btn:hover{background:#a80000}
        .menu{position:absolute;right:0;bottom:36px;min-width:200px;max-width:280px;max-height:340px;overflow:auto;
          background:#fff;color:#111;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.5);padding:6px;display:none}
        .open .menu{display:block}
        .t{padding:4px 8px;color:#555;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .menu button{display:block;width:100%;text-align:left;border:0;background:none;padding:7px 10px;
          border-radius:6px;cursor:pointer;color:#111}
        .menu button:hover{background:#f1f1f1}.menu .best{font-weight:700}
        .menu .hide{color:#777;font-size:11px;margin-top:4px;border-top:1px solid #eee;border-radius:0}
      </style><div id="layer"></div>`;
    layer = root.querySelector("#layer");
    document.documentElement.appendChild(hostEl);
  }

  const send = async (msg) => {
    try { return await chrome.runtime.sendMessage(msg); } catch (e) { return null; }
  };

  function permalinkFor(el) {
    let node = el;
    for (let i = 0; i < 14; i++) {
      node = node && node.parentElement;
      if (!node || node === document.documentElement) break;
      for (const a of node.querySelectorAll("a[href]")) {
        if (/^https?:/i.test(a.href) && a.hostname === location.hostname && PERMALINK.test(a.href)) return a.href;
      }
    }
    return "";
  }

  function candidates(el, t) {
    const out = [];
    const add = (u) => { if (u && /^https?:/i.test(u) && !out.includes(u)) out.push(u); };
    if (el.tagName === "IFRAME") { add(el.src); add(location.href); return out; }
    if (t.primary && SINGLE_PAGE.test(location.pathname + location.search)) add(location.href);
    add(permalinkFor(el));
    add(location.href);
    const src = el.currentSrc || el.src;
    if (src && !src.startsWith("blob:")) add(src);
    return out;
  }

  function makeTarget(el) {
    ensureLayer();
    const pill = document.createElement("div");
    pill.className = "pill";
    const btn = document.createElement("button");
    btn.className = "btn";
    const label = document.createElement("span");
    label.textContent = "Download";
    btn.appendChild(label);
    const menu = document.createElement("div");
    menu.className = "menu";
    pill.append(menu, btn);
    layer.appendChild(pill);
    const t = { pill, btn, menu, label, primary: false, busy: false };

    const note = (text) => { label.textContent = text; setTimeout(() => { label.textContent = "Download"; }, 3500); };
    const line = (text, cls) => { const d = document.createElement("div"); d.className = cls || "t"; d.textContent = text; return d; };
    const option = (text, q, url, cls) => {
      const b = document.createElement("button");
      b.textContent = text;
      if (cls) b.className = cls;
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        pill.classList.remove("open");
        label.textContent = "Sending...";
        const res = await send({ type: "ytdl-start", q, pl: false, url });
        if (!res || res.status === 0) note((res && res.text && res.text.length < 60) ? res.text : "Helper not running");
        else if (res.ok) note("Started");
        else note("Error " + res.status);
      });
      return b;
    };

    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (pill.classList.contains("open")) { pill.classList.remove("open"); return; }
      for (const o of targets.values()) o.pill.classList.remove("open");
      pill.classList.add("open");
      menu.replaceChildren(line("Detecting qualities..."));
      const urls = candidates(el, t);
      if (!urls.length) { menu.replaceChildren(line("No link found for this video")); return; }
      const res = await send({ type: "ytdl-formats", urls });
      menu.replaceChildren();
      let url = urls[0];
      if (res && res.ok && res.formats && res.formats.length) {
        url = res.url;
        if (res.title) menu.appendChild(line(res.title));
        const seen = new Set();
        menu.appendChild(option(`Best available (${res.formats[0].p}p)`, "4320", url, "best"));
        for (const f of res.formats) {
          if (seen.has(f.p)) continue;
          seen.add(f.p);
          menu.appendChild(option(`${f.p}p`, String(f.h), url));
        }
      } else {
        const why = res && res.text ? res.text.slice(0, 90) : "no answer from the helper";
        menu.appendChild(line("Could not detect qualities: " + why));
        for (const [q, l] of STANDARD) menu.appendChild(option(l, q, url));
      }
      menu.appendChild(option("MP3 audio only", "mp3", url));
      const hide = document.createElement("button");
      hide.className = "hide";
      hide.textContent = "Hide these buttons on this page";
      hide.addEventListener("click", () => { dismissed = true; hostEl.remove(); });
      menu.appendChild(hide);
    });
    return t;
  }

  function scan() {
    const found = new Set(document.querySelectorAll("video"));
    for (const f of document.querySelectorAll("iframe[src]")) if (PLAYER_IFRAME.test(f.src)) found.add(f);
    for (const [el, t] of targets) {
      if (!found.has(el) || !el.isConnected) { t.pill.remove(); targets.delete(el); }
    }
    for (const el of found) if (!targets.has(el)) targets.set(el, makeTarget(el));
  }

  function place() {
    const cw = document.documentElement.clientWidth, ch = document.documentElement.clientHeight;
    let top = null, topArea = 0;
    for (const [el, t] of targets) {
      const r = el.getBoundingClientRect();
      const iy = Math.min(r.bottom, ch) - Math.max(r.top, 0);
      const ix = Math.min(r.right, cw) - Math.max(r.left, 0);
      const ok = r.width >= MIN_W && r.height >= MIN_H && iy >= 100 && ix >= 100;
      t.visible = ok;
      t.area = ok ? ix * iy : 0;
      if (t.area > topArea) { topArea = t.area; top = t; }
      if (!ok) { t.pill.style.display = "none"; t.pill.classList.remove("open"); continue; }
      t.pill.style.display = "block";
      t.pill.style.right = Math.max(8, cw - Math.min(r.right, cw) + 8) + "px";
      t.pill.style.top = Math.min(r.bottom + 6, ch - 40) + "px";
    }
    for (const t of targets.values()) t.primary = t === top;
  }

  let queued = false;
  const schedule = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; place(); });
  };
  window.addEventListener("scroll", schedule, true);
  window.addEventListener("resize", schedule);
  document.addEventListener("click", () => { for (const t of targets.values()) t.pill.classList.remove("open"); });

  const timer = setInterval(() => {
    if (!chrome.runtime || !chrome.runtime.id) {
      clearInterval(timer);
      if (hostEl) hostEl.remove();
      return;
    }
    if (dismissed) return;
    scan();
    place();
  }, 700);
})();
