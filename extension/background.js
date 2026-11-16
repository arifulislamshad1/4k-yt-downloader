const HELPER = "http://127.0.0.1:9777/";
const NATIVE_HOST = "com.ytdl.helper";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function ping() {
  try {
    const r = await fetch(HELPER + "ping", { cache: "no-store", signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch (e) {
    return false;
  }
}

function askNativeHost() {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendNativeMessage(NATIVE_HOST, { cmd: "start" }, (res) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
}

let starting = null;
async function ensureHelper() {
  if (await ping()) return { ok: true };
  if (!starting) {
    starting = (async () => {
      try {
        const res = await askNativeHost();
        if (res && res.ok === false) return { ok: false, error: res.error || "helper did not start" };
      } catch (e) {
        return { ok: false, notInstalled: true, error: String(e.message || e) };
      }
      for (let i = 0; i < 40; i++) {
        if (await ping()) return { ok: true };
        await sleep(500);
      }
      return { ok: false, error: "helper did not start in time" };
    })().finally(() => { starting = null; });
  }
  return starting;
}

async function startDownload(msg) {
  try { chrome.storage.local.set({ q: msg.q }); } catch (e) {}
  const h = await ensureHelper();
  if (!h.ok) {
    const text = h.notInstalled
      ? "Helper is not running and auto-start is not set up. Open the helper app once, or reinstall it."
      : h.error;
    return { ok: false, status: 0, text };
  }
  const target =
    `${HELPER}?q=${encodeURIComponent(msg.q)}&pl=${msg.pl ? 1 : 0}` +
    `&url=${encodeURIComponent(msg.url)}`;
  try {
    const r = await fetch(target, { headers: { "X-YTDL": "1" } });
    return { ok: r.ok, status: r.status, text: await r.text() };
  } catch (e) {
    return { ok: false, status: 0, text: String(e) };
  }
}

async function getFormats(urls) {
  const h = await ensureHelper();
  if (!h.ok) {
    const text = h.notInstalled
      ? "Helper is not running and auto-start is not set up. Open the helper app once, or reinstall it."
      : h.error;
    return { ok: false, text };
  }
  let last = "could not read this video";
  for (const url of urls || []) {
    try {
      const r = await fetch(`${HELPER}formats?url=${encodeURIComponent(url)}`,
        { headers: { "X-YTDL": "1" }, signal: AbortSignal.timeout(100000) });
      const text = await r.text();
      if (r.ok) return { ok: true, url, ...JSON.parse(text) };
      last = text;
    } catch (e) {
      last = String(e);
    }
  }
  return { ok: false, text: last };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg) return;
  if (msg.type === "ytdl-start") { startDownload(msg).then(sendResponse); return true; }
  if (msg.type === "ytdl-formats") { getFormats(msg.urls).then(sendResponse); return true; }
});

function badge(text, color) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
}

function setupMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "ytdl-download",
      title: "Download with 4K YT Downloader",
      contexts: ["page", "video", "link"],
    });
  });
}

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "ytdl-download") return;
  const direct = info.srcUrl && /^https?:/i.test(info.srcUrl) ? info.srcUrl : "";
  const url = info.linkUrl || direct || info.pageUrl;
  if (!url) return;
  const { q } = await chrome.storage.local.get("q");
  badge("...", "#777777");
  const res = await startDownload({ q: q || "4320", pl: false, url });
  if (res.ok) badge("OK", "#0a7a0a");
  else badge("!", "#cc0000");
});

async function injectIntoOpenTabs() {
  try {
    const tabs = await chrome.tabs.query({ url: ["http://*/*", "https://*/*"] });
    for (const t of tabs) {
      const yt = /^https:\/\/(www|m)\.youtube\.com\//.test(t.url || "");
      if (/^https:\/\/music\.youtube\.com\//.test(t.url || "")) continue;
      try {
        await chrome.scripting.executeScript({
          target: { tabId: t.id },
          files: [yt ? "content.js" : "content_any.js"],
        });
      } catch (e) {}
    }
  } catch (e) {}
}
chrome.runtime.onInstalled.addListener(() => { setupMenu(); injectIntoOpenTabs(); });
chrome.runtime.onStartup.addListener(() => { setupMenu(); injectIntoOpenTabs(); });
