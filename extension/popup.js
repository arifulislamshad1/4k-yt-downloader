const $ = (id) => document.getElementById(id);
const YT_HOSTS = new Set([
  "www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be",
]);

(function showBrand() {
  const B = typeof BRAND !== "undefined" ? BRAND : {};
  if (B.app_name) { $("name").textContent = B.app_name; document.title = B.app_name; }
  if (B.creator) $("by").textContent = "Created by " + B.creator;
  const wrap = $("links");
  const add = (label, url) => {
    if (!url || url.includes("YOUR_")) return;
    const a = document.createElement("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = label;
    wrap.appendChild(a);
  };
  add("Facebook", B.facebook);
  add("GitHub", B.github);
  const digits = (B.whatsapp || "").replace(/\D/g, "").replace(/^0+/, "");
  if (digits) add("WhatsApp", "https://wa.me/" + digits);
  if (!wrap.children.length) $("foot").style.display = "none";
})();

function isVideoPage(raw) {
  let u;
  try { u = new URL(raw); } catch { return false; }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  if (!YT_HOSTS.has(u.hostname)) return true;
  if (u.hostname === "youtu.be") return u.pathname.length > 1;
  if (u.pathname === "/watch") return u.searchParams.has("v");
  if (u.pathname === "/playlist") return u.searchParams.has("list");
  return /^\/(shorts|live|embed)\/[\w-]+/.test(u.pathname);
}

function status(msg, kind = "") {
  const el = $("s");
  el.textContent = msg;
  el.className = kind;
}

$("q").value = localStorage.getItem("q") || "4320";
$("pl").checked = localStorage.getItem("pl") === "1";

$("go").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab && tab.url;

  if (!url || !isVideoPage(url)) {
    status("Open a page that has a video (http/https) first.", "err");
    return;
  }

  const q = $("q").value;
  const pl = $("pl").checked ? 1 : 0;
  localStorage.setItem("q", q);
  localStorage.setItem("pl", String(pl));

  $("go").disabled = true;
  status("Sending... (starting the helper if needed)");

  try {
    const res = await chrome.runtime.sendMessage({ type: "ytdl-start", q, pl, url });
    if (res && res.ok) status("Started. Watch the helper app window for progress.", "ok");
    else if (res && res.status) status("Helper refused the request (HTTP " + res.status + ").", "err");
    else status((res && res.text) || "Could not reach the helper.", "err");
  } catch (e) {
    status("Could not reach the helper: " + e.message, "err");
  } finally {
    $("go").disabled = false;
  }
});
