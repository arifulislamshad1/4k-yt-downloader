(() => {
  "use strict";

  if (window.__ytdlLoaded) return;
  window.__ytdlLoaded = true;

  const BOX_ID = "ytdl-helper-box";
  const KEY = "ytdl_helper_quality";
  const QUALITIES = [
    ["4320", "Best available"], ["2160", "4K (2160p)"], ["1440", "1440p"], ["1080", "1080p"],
    ["720", "720p"], ["480", "480p"], ["mp3", "MP3 only"],
  ];

  const css = document.createElement("style");
  css.textContent = `
    #${BOX_ID}{display:inline-flex;align-items:center;gap:6px;margin-right:8px;height:36px;
      padding:0 4px 0 10px;border-radius:18px;box-sizing:border-box;
      background:var(--yt-spec-badge-chip-background,#f2f2f2);
      color:var(--yt-spec-text-primary,#0f0f0f);font:500 14px Roboto,Arial,sans-serif}
    #${BOX_ID} select{height:28px;border:0;border-radius:14px;padding:0 6px;font:inherit;cursor:pointer;
      background:transparent;color:inherit}
    #${BOX_ID} select option{color:#000}
    #${BOX_ID} label{display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer}
    #${BOX_ID} button{height:28px;border:0;border-radius:14px;padding:0 14px;font:inherit;
      cursor:pointer;background:#cc0000;color:#fff}
    #${BOX_ID} button:hover{background:#a80000}
    #${BOX_ID} button:disabled{background:#777;cursor:default}
  `;
  (document.head || document.documentElement).appendChild(css);

  function build() {
    const box = document.createElement("div");
    box.id = BOX_ID;
    box.dataset.href = location.href;

    const sel = document.createElement("select");
    sel.title = "Quality";
    for (const [value, label] of QUALITIES) {
      const o = document.createElement("option");
      o.value = value;
      o.textContent = label;
      sel.appendChild(o);
    }
    try { sel.value = localStorage.getItem(KEY) || "4320"; } catch (e) {}
    box.appendChild(sel);

    let detecting = false;
    box.addEventListener("mouseenter", async () => {
      if (detecting) return;
      detecting = true;
      try {
        const res = await chrome.runtime.sendMessage({ type: "ytdl-formats", urls: [location.href] });
        if (!res || !res.ok || !res.formats || !res.formats.length) { detecting = false; return; }
        const keep = sel.value;
        sel.replaceChildren();
        const add = (v, l) => { const o = document.createElement("option"); o.value = v; o.textContent = l; sel.appendChild(o); };
        add("4320", `Best available (${res.formats[0].p}p)`);
        const seen = new Set();
        for (const f of res.formats) { if (!seen.has(f.p)) { seen.add(f.p); add(String(f.h), `${f.p}p`); } }
        add("mp3", "MP3 only");
        sel.value = [...sel.options].some((o) => o.value === keep) ? keep : "4320";
      } catch (e) { detecting = false; }
    });

    let plCheck = null;
    if (new URL(location.href).searchParams.has("list")) {
      const lab = document.createElement("label");
      plCheck = document.createElement("input");
      plCheck.type = "checkbox";
      lab.appendChild(plCheck);
      lab.appendChild(document.createTextNode("Playlist"));
      box.appendChild(lab);
    }

    const btn = document.createElement("button");
    btn.type = "button";
    const IDLE = "Download";
    btn.textContent = IDLE;
    const flash = (text) => {
      btn.textContent = text;
      setTimeout(() => { btn.textContent = IDLE; btn.disabled = false; }, 3000);
    };

    btn.addEventListener("click", () => {
      try { localStorage.setItem(KEY, sel.value); } catch (e) {}
      btn.disabled = true;
      btn.textContent = "Sending...";
      try {
        chrome.runtime.sendMessage(
          { type: "ytdl-start", q: sel.value, pl: plCheck ? plCheck.checked : false, url: location.href },
          (res) => {
            if (chrome.runtime.lastError || !res || res.status === 0) flash("Helper not running");
            else if (res.ok) flash("Started");
            else flash("Error " + res.status);
          }
        );
      } catch (e) {
        flash("Reload the page");
      }
    });

    box.appendChild(btn);
    return box;
  }

  function ensure() {
    if (!chrome.runtime || !chrome.runtime.id) {
      clearInterval(timer);
      return;
    }
    const existing = document.getElementById(BOX_ID);
    if (location.pathname !== "/watch") {
      if (existing) existing.remove();
      return;
    }
    const host =
      document.querySelector("ytd-watch-metadata #top-level-buttons-computed") ||
      document.querySelector("ytd-watch-metadata #actions") ||
      document.querySelector("ytd-watch-metadata #above-the-fold");
    if (!host) return;
    if (existing && existing.dataset.href === location.href && host.contains(existing)) return;
    if (existing) existing.remove();
    host.prepend(build());
  }

  window.addEventListener("yt-navigate-finish", ensure);
  const timer = setInterval(ensure, 1000);
  const old = document.getElementById(BOX_ID);
  if (old) old.remove();
  ensure();
})();
