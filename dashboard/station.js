const STORE_KEY = "forgemind-demo-events";
const config = JSON.parse(document.querySelector("#station-config").textContent);
const api = new URLSearchParams(location.search).get("api") || localStorage.getItem("forgemind-core-api") || "";
const toast = document.querySelector("#toast");

function nextKit() {
  const n = Number(localStorage.getItem("forgemind-kit-number") || 23);
  return `KIT-${String(n).padStart(3, "0")}`;
}

async function send(action) {
  const button = document.querySelector(`[data-action="${action.id}"]`);
  button.disabled = true;
  const payload = { station: config.station, action: action.id, kit_id: nextKit(), detail: action.detail, timestamp: new Date().toISOString() };
  try {
    if (api) {
      const response = await fetch(`${api.replace(/\/$/, "")}/api/station/actions`, { method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(`Core returned HTTP ${response.status}`);
      show(`Accepted by Core: ${action.label}`, "ok");
    } else {
      const list = JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
      list.push({ station: config.station, action: action.id, kit: payload.kit_id, state: action.state, detail: action.detail, at: Date.now() });
      localStorage.setItem(STORE_KEY, JSON.stringify(list.slice(-50)));
      show(`Demo mode: ${action.label} saved locally`, "ok");
    }
    if (action.advance) {
      const n = Number(localStorage.getItem("forgemind-kit-number") || 23) + 1;
      localStorage.setItem("forgemind-kit-number", n);
      document.querySelector("#kit-id").textContent = nextKit();
    }
  } catch (error) { show(`Not sent: ${error.message}. Check Core API or use demo mode.`, "error"); }
  finally { button.disabled = false; }
}

function show(message, type) { toast.textContent = message; toast.className = `toast ${type}`; }

document.title = `${config.title} · ForgeMind`;
document.querySelector("#station-name").textContent = config.title;
document.querySelector("#station-purpose").textContent = config.purpose;
document.querySelector("#kit-id").textContent = nextKit();
document.querySelector("#mode").textContent = api ? "Core connected" : "Demo mode";
document.querySelector("#actions").innerHTML = config.actions.map(a => `<button class="action ${a.kind || ""}" data-action="${a.id}">${a.label}</button>`).join("");
config.actions.forEach(a => document.querySelector(`[data-action="${a.id}"]`).addEventListener("click", () => send(a)));
