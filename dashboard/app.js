const STORE = "forgemind-demo-events";

const seed = [
  { station: "alice", action: "kit_inspected", kit: "KIT-021", state: "ready", detail: "Complete kit verified", at: Date.now() - 58000 },
  { station: "recovery", action: "reinspection_failed", kit: "KIT-022", state: "held", detail: "Missing black wheel", at: Date.now() - 31000 },
  { station: "recovery", action: "governor_approved", kit: "KIT-023", state: "recovery", detail: "Add one black wheel", at: Date.now() - 12000 }
];

function events() {
  try { return JSON.parse(localStorage.getItem(STORE)) || seed; }
  catch { return seed; }
}

function renderTickets() {
  const root = document.querySelector("#tickets");
  if (!root) return;
  root.innerHTML = events().slice(-5).reverse().map(e => `
    <article class="ticket">
      <strong>${e.kit}</strong>
      <div><strong>${e.detail}</strong><div class="muted">${e.station} · ${new Date(e.at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}</div></div>
      <span class="state ${e.state}">${e.state.toUpperCase()}</span>
    </article>`).join("");
}

function initTabs() {
  document.querySelectorAll(".tab").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === btn));
    document.querySelectorAll(".tab-panel").forEach(p => { p.hidden = p.id !== btn.dataset.tab; });
  }));
}

renderTickets();
initTabs();
window.addEventListener("storage", renderTickets);
