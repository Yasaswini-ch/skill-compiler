// The panel: shows the selected text, runs the chosen skill on the local server and renders the steps as they arrive.
const SERVER = "http://127.0.0.1:5000";
const $ = id => document.getElementById(id);
let skills = [], collected = [], controller = null;

const store = {
  async get(area, key) { try { return (await chrome.storage[area].get(key))[key]; } catch (_) { return undefined; } },
  async set(area, obj) { try { await chrome.storage[area].set(obj); } catch (_) { /* storage is optional */ } },
};

function render(state) {
  const list = $("steps");
  list.replaceChildren(...state.steps.map(s => {
    const li = document.createElement("li");
    li.dataset.state = s.state;
    const badge = document.createElement("span");
    badge.className = "badge"; badge.textContent = PanelCore.label(s.state);
    li.append(`${s.id}. ${s.title}`, badge);
    if (s.note && s.state !== "pass") {
      const n = document.createElement("div");
      n.className = "note";
      n.textContent = (s.state === "repaired" ? "First try rejected: " : s.state === "fail" ? "Rejected: " : "Rejected, retrying: ") + s.note;
      li.append(n);
    }
    return li;
  }));
  $("err").textContent = state.error || "";
  if (state.finalOutput !== null) {
    $("result").hidden = false;
    $("final").textContent = (state.mock ? "[MOCK] " : "") + state.finalOutput;
  }
}

function describeNetworkError(e) {
  if (e.name === "AbortError") return "Stopped.";
  return "Could not reach the Skill Compiler server on this computer. Start it with:  python web/server.py  and try again.";
}

async function run() {
  const input = $("input").value;
  const skill = skills.find(s => s.id === $("skill").value);
  if (!input.trim()) { $("err").textContent = "There is no text to run the skill on."; return; }
  if (!skill) { $("err").textContent = "Pick a skill."; return; }
  $("run").disabled = true; $("err").textContent = ""; $("result").hidden = true; $("status").textContent = "Running…";
  collected = []; controller = new AbortController();
  let state = PanelCore.initialState();
  render(state);
  try {
    const res = await fetch(`${SERVER}/extension/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill_text: skill.text, input }), signal: controller.signal,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw Object.assign(new Error(data.error || `The server answered ${res.status}.`), { server: true });
    }
    const reader = res.body.getReader(), decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const { lines, rest } = PanelCore.takeLines(buffer, decoder.decode(value, { stream: true }));
      buffer = rest;
      for (const line of lines) {
        const e = PanelCore.parseLine(line);
        if (!e) continue;
        collected.push(line);
        state = PanelCore.applyEvent(state, e);
        render(state);
      }
    }
    if (!state.done) { state = { ...state, error: "The run ended without a result.", done: true }; render(state); }
  } catch (e) {
    $("err").textContent = e.server ? e.message : describeNetworkError(e);
  } finally {
    $("run").disabled = false; $("status").textContent = "";
    if (collected.length) $("download").disabled = false;
  }
}

function download() {
  const blob = new Blob([collected.join("\n") + "\n"], { type: "application/x-ndjson" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "skill-compiler-events.ndjson";
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function showSkillDescription() {
  const s = skills.find(x => x.id === $("skill").value);
  $("skillDesc").textContent = s ? s.description : "";
}

async function init() {
  $("accept").addEventListener("click", async () => { await store.set("local", { acknowledged: true }); $("notice").hidden = true; $("main").hidden = false; });
  $("run").addEventListener("click", run);
  $("download").addEventListener("click", download);
  $("skill").addEventListener("change", showSkillDescription);
  $("input").addEventListener("input", () => { $("count").textContent = `(${$("input").value.length} / 1500 characters)`; });

  const selection = (await store.get("session", "selection")) || "";
  $("input").value = selection.length > 1500 ? selection.slice(0, 1500) : selection;
  if (selection.length > 1500) $("err").textContent = `Your selection is ${selection.length} characters; only the first 1500 are used.`;
  $("count").textContent = `(${$("input").value.length} / 1500 characters)`;

  try {
    const index = await (await fetch(chrome.runtime.getURL("skills/index.json"))).json();
    skills = await Promise.all(index.map(async s => ({ ...s, text: await (await fetch(chrome.runtime.getURL(`skills/${s.file}`))).text() })));
  } catch (_) { $("err").textContent = "Could not load the bundled skills."; }
  for (const s of skills) { const o = document.createElement("option"); o.value = s.id; o.textContent = s.title; $("skill").append(o); }
  showSkillDescription();
  $("download").disabled = true;

  const accepted = await store.get("local", "acknowledged");
  $("notice").hidden = !!accepted; $("main").hidden = !accepted;
}
init();
