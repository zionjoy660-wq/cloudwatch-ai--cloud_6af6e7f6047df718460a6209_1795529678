/* CloudWatch AI – frontend logic (plain JavaScript, no framework). */

let updatesCache = [];
let appStatus = null;

const DEFAULT_PROFILE = {
  team_name: "Cloud Platform Team",
  services: ["AWS", "Azure", "Google Cloud", "Kubernetes", "Terraform"],
  projects: ["cloud migration", "container platform", "observability"],
  risk_tolerance: "moderate",
  additional_context: "",
};
let profile = { ...DEFAULT_PROFILE };

const $ = (id) => document.getElementById(id);

/* ---------- small helpers ---------- */

// Escape text before putting it into innerHTML, so user/LLM text can never become HTML.
function esc(value) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(value ?? "").replace(/[&<>"']/g, (c) => map[c]);
}

// Only allow http(s) links (blocks javascript: and similar).
function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : "";
  } catch (e) {
    return "";
  }
}

function linkChip(url, label) {
  const href = safeUrl(url);
  return href
    ? `<a class="chip link" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`
    : `<span class="chip">NO SOURCE LINK</span>`;
}

let toastTimer = null;
function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

// Calls the backend and returns parsed JSON. Throws an Error with a readable message on any failure.
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (e) {
    throw new Error("Cannot reach the server. Is it running?");
  }
  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    if (response.ok) throw new Error("The server sent an unreadable response.");
  }
  if (!response.ok) {
    let detail = data && data.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg || "invalid value").join("; ");
    throw new Error(detail || `Request failed (HTTP ${response.status}).`);
  }
  return data;
}

function postJson(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

// Disables a button while an action runs, so it cannot be clicked twice.
async function withBusy(button, busyLabel, action) {
  if (button.disabled) return;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

/* ---------- navigation ---------- */

const TITLES = {
  overview: "Overview",
  updates: "Cloud updates",
  digest: "Release digest",
  ask: "Ask a question",
  memory: "Team memory",
  evaluation: "Evaluation",
};

function switchView(view) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $(view).classList.add("active");
  document.querySelectorAll(".nav").forEach((n) => {
    const active = n.dataset.view === view;
    n.classList.toggle("active", active);
    if (active) n.setAttribute("aria-current", "page");
    else n.removeAttribute("aria-current");
  });
  $("pageTitle").textContent = TITLES[view];
  if (view === "memory") loadMemory();
  if (view === "evaluation") loadEval();
  if (view === "updates") renderUpdates();
}
document.querySelectorAll(".nav").forEach((n) => (n.onclick = () => switchView(n.dataset.view)));

/* ---------- team profile (saved in this browser) ---------- */

function splitList(text) {
  return text.split(",").map((x) => x.trim()).filter(Boolean);
}

function getProfile() {
  return {
    ...profile,
    team_name: $("teamName").value.trim() || DEFAULT_PROFILE.team_name,
    services: splitList($("teamServices").value),
    projects: splitList($("teamProjects").value),
    additional_context: $("teamContext").value,
  };
}

function fillProfileForm() {
  $("teamName").value = profile.team_name || "";
  $("teamServices").value = (profile.services || []).join(", ");
  $("teamProjects").value = (profile.projects || []).join(", ");
  $("teamContext").value = profile.additional_context || "";
}

$("saveProfile").onclick = () => {
  const p = getProfile();
  if (!p.services.length && !p.projects.length) {
    toast("Add at least one service or project so results can be personalised.");
    return;
  }
  profile = p;
  try {
    localStorage.setItem("cw-profile", JSON.stringify(profile));
    toast("Profile saved in this browser.");
  } catch (e) {
    toast("Could not save in this browser (storage blocked). The profile is still used for this session.");
  }
};

function loadSavedProfile() {
  try {
    const saved = JSON.parse(localStorage.getItem("cw-profile") || "null");
    if (saved && typeof saved === "object") {
      profile = {
        ...DEFAULT_PROFILE,
        ...saved,
        services: Array.isArray(saved.services) ? saved.services : DEFAULT_PROFILE.services,
        projects: Array.isArray(saved.projects) ? saved.projects : DEFAULT_PROFILE.projects,
      };
    }
  } catch (e) {
    profile = { ...DEFAULT_PROFILE }; // damaged saved data: start from the defaults
  }
  fillProfileForm();
}

/* ---------- status, mode banner ---------- */

function renderBanner(s) {
  const banner = $("modeBanner");
  const analysis = s.analysis_mode === "llm" ? "AI analysis: LLM" : "AI analysis: local rule-based fallback (no LLM call)";
  let kind = "demo";
  let text;
  if (s.mode === "live") {
    kind = "live";
    text = "LIVE: collected from official provider pages by Firecrawl. Entries are cut automatically from each page, so boundaries can be imperfect; check the source link.";
  } else if (s.mode === "demo_fallback") {
    kind = "warn";
    text = "LIVE COLLECTION DID NOT HAPPEN: showing illustrative sample data instead.";
  } else if (s.mode === "demo") {
    text = "DEMO MODE: all records are illustrative samples, not real cloud announcements.";
  } else if (s.demo_mode) {
    text = "DEMO MODE: Collect updates will load illustrative samples (no API keys needed).";
  } else if (s.firecrawl_configured) {
    kind = "live";
    text = "LIVE MODE: Collect updates will scrape the official provider pages with Firecrawl.";
  } else {
    kind = "warn";
    text = "LIVE MODE is selected but FIRECRAWL_API_KEY is missing: Collect updates will fall back to illustrative samples.";
  }
  const warnings = (s.warnings || []).filter((w) => !/^Demo mode:/.test(w));
  banner.className = `banner ${kind}`;
  banner.innerHTML =
    `<strong>${esc(text)}</strong> <span>${esc(analysis)}</span>` +
    (warnings.length ? `<ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : "");
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    appStatus = s;
    $("metricUpdates").textContent = s.updates;
    $("metricMemory").textContent = s.memory_records;
    $("metricMode").textContent = s.mode.replaceAll("_", " ").toUpperCase();
    $("modeTag").textContent =
      s.mode === "live" ? "LIVE DATA" : s.mode === "demo" || s.mode === "demo_fallback" ? "SAMPLE DATA" : s.demo_mode ? "DEMO MODE" : "LIVE MODE";
    $("sideStatus").textContent = s.mode === "not_collected" ? "Ready" : s.mode.replaceAll("_", " ");
    renderBanner(s);
  } catch (e) {
    $("sideStatus").textContent = "Server unreachable";
    $("modeBanner").className = "banner warn";
    $("modeBanner").textContent = e.message;
  }
}

/* ---------- collecting and listing updates ---------- */

$("collectBtn").onclick = () =>
  withBusy($("collectBtn"), "Collecting…", async () => {
    try {
      const r = await postJson("/api/collect", {});
      updatesCache = r.updates;
      toast(`${r.count} records collected (${r.mode.replaceAll("_", " ")})`);
      await refreshStatus();
      renderUpdates();
    } catch (e) {
      toast("Collection failed: " + e.message);
    }
  });

async function loadUpdates() {
  try {
    updatesCache = (await api("/api/updates")).updates;
  } catch (e) {
    updatesCache = [];
  }
  renderUpdates();
}

function showEmpty(el, message) {
  el.className = el.className.replace(/\bempty-state\b/g, "").trim() + " empty-state";
  el.textContent = message;
}

function renderUpdates() {
  const list = $("updatesList");
  if (!updatesCache.length) {
    showEmpty(list, "No updates yet. Click “Collect updates” (top right) to load them.");
    return;
  }
  const q = $("searchUpdates").value.trim().toLowerCase();
  const provider = $("providerFilter").value;
  const category = $("categoryFilter").value;
  const shown = updatesCache.filter((u) => {
    const text = `${u.title} ${u.summary} ${u.content} ${(u.services || []).join(" ")}`.toLowerCase();
    return (!q || text.includes(q)) && (!provider || u.provider === provider) && (!category || u.category === category);
  });
  list.className = "update-list";
  if (!shown.length) {
    showEmpty(list, "No updates match the search or filters. Clear them to see all updates.");
    return;
  }
  list.innerHTML = shown
    .map((u) => {
      const date = u.published_at ? `<span class="chip">${esc(u.published_at.slice(0, 10))}</span>` : "";
      const note = u.is_demo
        ? '<span class="chip demo">ILLUSTRATIVE SAMPLE · NOT A REAL ANNOUNCEMENT</span>'
        : u.collection_type === "page_capture"
          ? '<span class="chip">WHOLE-PAGE CAPTURE</span>'
          : u.collection_type === "release_note"
            ? '<span class="chip">RELEASE NOTE (auto-split)</span>'
            : "";
      return `<article class="update-card">
        <div>
          <span class="eyebrow">${esc(u.provider)} / ${esc(u.category)}</span>
          <h3>${esc(u.title)}</h3>
          <p>${esc((u.summary || u.content || "").slice(0, 360))}</p>
          <div class="update-meta">
            ${note}${date}
            <span class="chip">${esc((u.services || []).join(", ") || "Services not detected")}</span>
            ${linkChip(u.url, u.is_demo ? "PROVIDER SITE" : "SOURCE")}
          </div>
        </div>
        <button type="button" class="button secondary analyze-btn" data-id="${esc(u.id)}">Analyze</button>
      </article>`;
    })
    .join("");
}

["searchUpdates", "providerFilter", "categoryFilter"].forEach((id) => ($(id).oninput = renderUpdates));

// One click handler for all "Analyze" buttons.
$("updatesList").addEventListener("click", (event) => {
  const button = event.target.closest(".analyze-btn");
  if (button) analyzeOne(button);
});

/* ---------- analysis and digest ---------- */

async function analyzeOne(button) {
  await withBusy(button, "Analyzing…", async () => {
    try {
      const a = await postJson("/api/analyze", { update_id: button.dataset.id, team_profile: getProfile() });
      $("digestResult").className = "digest-result";
      $("digestResult").innerHTML = `<h3 class="list-title">Single update analysis</h3>${analysisHTML(a)}`;
      switchView("digest");
      toast("Analysis saved to team memory.");
      refreshStatus();
    } catch (e) {
      toast("Analysis failed: " + e.message);
    }
  });
}

function listBlock(label, items) {
  return items && items.length ? `<p><b>${label}</b></p><ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
}

function analysisHTML(a) {
  const priority = ["High", "Medium", "Low"].includes(a.priority) ? a.priority : "Low";
  const score = Number(a.relevance_score) || 0;
  const matches = (a.team_matches || []).join(", ");
  const mode = a.analysis_mode === "llm" ? "LLM ANALYSIS" : "LOCAL RULE-BASED ANALYSIS";
  return `<article class="analysis-card">
    <div class="analysis-top">
      <div>
        <span class="eyebrow">${esc(a.provider)} / ${esc(a.change_type)} / ${mode}</span>
        <h3>${esc(a.title || "Analysis")}</h3>
      </div>
      <span class="priority ${priority.toLowerCase()}">${priority} · ${score}%</span>
    </div>
    ${a.data_notice ? `<p class="notice">${esc(a.data_notice)}</p>` : ""}
    ${a.llm_error ? `<p class="notice">The LLM call failed, so the local analysis was used instead (${esc(a.llm_error)}).</p>` : ""}
    <p><b>Summary:</b> ${esc(a.change_summary)}</p>
    ${listBlock("Stated in the announcement:", a.evidence)}
    <p><b>Matches your team profile:</b> ${esc(matches || "No direct match")}</p>
    <p><b>Possible impact (inferred, not verified):</b> ${esc(a.organizational_impact)}</p>
    <p><b>Related memory:</b> ${esc((a.historical_context || []).join("; ") || "No related memory retrieved.")}</p>
    <p><b>Confidence:</b> ${esc(a.confidence)}</p>
    ${listBlock("Recommended actions:", a.recommended_actions)}
    <div class="update-meta">
      ${a.is_demo ? '<span class="chip demo">ILLUSTRATIVE DATA</span>' : ""}
      ${linkChip(a.source_url, a.is_demo ? "PROVIDER SITE" : "OPEN SOURCE")}
    </div>
  </article>`;
}

$("generateDigest").onclick = () => {
  if (!updatesCache.length) {
    toast("Collect updates first.");
    return;
  }
  return withBusy($("generateDigest"), "Analyzing…", async () => {
    try {
      const r = await postJson("/api/digest", { team_profile: getProfile(), days: 30 });
      const groups = [["high_priority", "HIGH"], ["medium_priority", "MEDIUM"], ["low_priority", "LOW"]];
      $("digestResult").className = "digest-result";
      $("digestResult").innerHTML =
        `<div class="digest-summary">${esc(r.executive_summary)}</div>` +
        groups
          .map(([key, label]) => `<div><h3 class="eyebrow">${label} PRIORITY · ${r[key].length}</h3>` +
            (r[key].map(analysisHTML).join("") || '<div class="empty-state">No items in this group.</div>') + "</div>")
          .join("");
      $("metricHigh").textContent = r.high_priority.length;
      toast("Digest generated.");
      refreshStatus();
    } catch (e) {
      toast("Digest failed: " + e.message);
    }
  });
};

/* ---------- ask a question ---------- */

function askResultHTML(r) {
  const modeLabel = { llm: "LLM ANSWER", local_fallback: "LOCAL KEYWORD SEARCH (NO LLM)", no_match: "NO MATCH" }[r.mode] || "ANSWER";
  const sources = (r.sources || [])
    .map((s) => `<li>[${esc(s.n)}] ${esc(s.title)} <span class="muted">(${esc(s.provider)}${s.is_demo ? ", illustrative sample" : ""})</span> ${linkChip(s.url, "SOURCE")}</li>`)
    .join("");
  return `<article class="analysis-card">
    <span class="eyebrow">${modeLabel}</span>
    <h3>${esc(r.question)}</h3>
    ${r.notice ? `<p class="notice">${esc(r.notice)}</p>` : ""}
    ${r.llm_error ? `<p class="notice">The LLM call failed, so a keyword search was used instead (${esc(r.llm_error)}).</p>` : ""}
    ${r.llm_warning ? `<p class="notice">${esc(r.llm_warning)}</p>` : ""}
    <p class="answer-text">${esc(r.answer)}</p>
    ${sources ? `<p><b>Sources used:</b></p><ul>${sources}</ul>` : ""}
    ${(r.team_context || []).length ? `<p><b>Team context used:</b> ${esc(r.team_context.join("; "))}</p>` : ""}
  </article>`;
}

const ASK_DEFAULT_TEXT = "Collect updates, then ask a question.";
let askShowsMessage = false; // true while the result area shows a validation/error message

// Replaces whatever is in the result area (an old answer, for example) with a plain message.
function showAskMessage(message, isValidation = false) {
  const box = $("askResult");
  box.className = "empty-state";
  box.textContent = message;
  askShowsMessage = isValidation;
}

// Typing in the question box: clearing it removes the old answer; typing again removes a validation message.
function onAskInput() {
  if ($("askQuestion").value.trim() === "") showAskMessage(ASK_DEFAULT_TEXT);
  else if (askShowsMessage) showAskMessage(ASK_DEFAULT_TEXT);
}
$("askQuestion").addEventListener("input", onAskInput);

$("askBtn").onclick = () => {
  const question = $("askQuestion").value.trim();
  if (question.length < 3) {
    const message = question === "" ? "Please type a question first, then press Ask." : "Please type a longer question (at least 3 characters).";
    showAskMessage(message, true);   // the old answer must not stay on screen
    toast(message);
    return;
  }
  if (!updatesCache.length) {
    showAskMessage("Collect updates first, then ask a question.", true);
    toast("Collect updates first.");
    return;
  }
  return withBusy($("askBtn"), "Thinking…", async () => {
    showAskMessage("Looking for an answer…");   // remove the previous answer while the new one is prepared
    try {
      const r = await postJson("/api/ask", { question, team_profile: getProfile() });
      $("askResult").className = "digest-result";
      $("askResult").innerHTML = askResultHTML(r);
      askShowsMessage = false;
    } catch (e) {
      showAskMessage("The question could not be answered: " + e.message, true);
      toast("Question failed: " + e.message);
    }
  });
};

$("askExamples").addEventListener("click", (event) => {
  const chip = event.target.closest(".example");
  if (chip) {
    $("askQuestion").value = chip.dataset.q;
    onAskInput();
  }
});

/* ---------- team memory ---------- */

function memoryItemHTML(m) {
  const demo = m.is_demo ? '<span class="chip demo">ILLUSTRATIVE</span>' : "";
  const services = (m.services || []).length ? `<span class="chip">${esc(m.services.join(", "))}</span>` : "";
  return `<div class="memory-item">
    <span class="eyebrow">${esc((m.created_at || "").slice(0, 16).replace("T", " "))} UTC</span>
    <h3>${esc(m.title)}</h3><p>${esc(m.content)}</p>${services}${demo}</div>`;
}

function fillMemoryList(el, records, emptyText) {
  if (!records.length) {
    showEmpty(el, emptyText);
    return;
  }
  el.className = "memory-list";
  el.innerHTML = records.map(memoryItemHTML).join("");
}

async function loadMemory() {
  try {
    const r = await api("/api/memory");
    fillMemoryList($("contextList"), r.records.filter((m) => m.memory_type === "team_context"),
      "No team context saved yet. Add architecture facts or decisions above.");
    fillMemoryList($("analysisList"), r.records.filter((m) => m.memory_type === "reviewed_analysis"),
      "No analyses saved yet. Analyze an update or generate a digest.");
  } catch (e) {
    showEmpty($("contextList"), "Could not load memory: " + e.message);
  }
}

$("addMemory").onclick = () => {
  const content = $("memoryContent").value.trim();
  if (!content) {
    toast("Enter the context text first.");
    return;
  }
  const body = {
    title: $("memoryTitle").value.trim() || "Team context",
    content,
    services: splitList($("memoryServices").value),
  };
  return withBusy($("addMemory"), "Saving…", async () => {
    try {
      const r = await postJson("/api/memory", body);
      toast(r.message);
      $("memoryTitle").value = "";
      $("memoryContent").value = "";
      $("memoryServices").value = "";
      loadMemory();
      refreshStatus();
    } catch (e) {
      toast("Could not save: " + e.message);
    }
  });
};

/* ---------- evaluation ---------- */

function distributionHTML(title, counts) {
  const entries = Object.entries(counts || {});
  const chips = entries.length
    ? entries.map(([k, v]) => `<span class="chip">${esc(k)}: ${esc(v)}</span>`).join(" ")
    : "<span class='muted'>Nothing collected yet.</span>";
  return `<h4>${title}</h4><div class="chip-row">${chips}</div>`;
}

function analysisEvalHTML(s) {
  if (!s || !s.analyses_generated) {
    return "<h4>Analysis quality checks</h4><p class='muted'>No analyses generated yet. Analyze an update or generate a digest.</p>";
  }
  const problems = Object.entries(s.output_check_problems || {})
    .map(([title, list]) => `<li>${esc(title)}: ${esc(list.join("; "))}</li>`).join("");
  return `<h4>Analysis quality checks (automatic)</h4><div class="chip-row">
      <span class="chip">analyses: ${esc(s.analyses_generated)}</span>
      <span class="chip">passed output checks: ${esc(s.passed_output_checks)}/${esc(s.analyses_generated)}</span>
      <span class="chip">used memory context: ${esc(s.used_memory_context)}</span>
      <span class="chip">matched team profile: ${esc(s.with_team_match)}</span>
      <span class="chip">LLM: ${esc(s.llm_analyses)} · local: ${esc(s.local_analyses)} · LLM failures: ${esc(s.llm_failures)}</span></div>
    ${problems ? `<ul>${problems}</ul>` : ""}`;
}

function performanceHTML(perf) {
  const rows = Object.entries(perf || {});
  if (!rows.length) return "";
  return `<h4>API response time (measured in this session)</h4><div class="chip-row">${rows
    .map(([path, v]) => `<span class="chip">${esc(path)}: avg ${esc(v.avg_ms)} ms · max ${esc(v.max_ms)} ms · ${esc(v.calls)} calls</span>`)
    .join("")}</div>`;
}

async function loadEval() {
  try {
    const r = await api("/api/evaluation");
    const p = r.pipeline || {};
    $("evaluationMetrics").innerHTML = [
      ["COLLECTED", r.collected_updates], ["LIVE RECORDS", r.live_records],
      ["DEMO RECORDS", r.demo_records], ["MEMORY RECORDS", r.memory_records],
    ].map(([k, v]) => `<div class="metric"><span>${k}</span><strong>${v}</strong></div>`).join("");
    $("evaluationBreakdown").innerHTML =
      distributionHTML("Providers", r.provider_distribution) +
      distributionHTML("Categories", r.category_distribution) +
      `<h4>Preparation (Pandas)</h4><div class="chip-row">
        <span class="chip">raw records: ${esc(p.raw_count ?? 0)}</span>
        <span class="chip">empty removed: ${esc(p.empty_removed ?? 0)}</span>
        <span class="chip">duplicates removed: ${esc(p.duplicates_removed ?? 0)}</span>
        <span class="chip">with services detected: ${esc(r.records_with_services)}</span></div>
      <h4>Memory</h4><div class="chip-row">
        <span class="chip">team context: ${esc(r.team_context_records)}</span>
        <span class="chip">past analyses: ${esc(r.analysis_records)}</span></div>
      <h4>Analysis method</h4><div class="chip-row"><span class="chip">${r.analysis_mode === "llm" ? "LLM" : "local rule-based fallback"}</span></div>
      ${analysisEvalHTML(r.analysis_summary)}
      ${performanceHTML(r.performance)}
      <p class="muted">${esc(r.notes)}</p>`;
  } catch (e) {
    $("evaluationBreakdown").textContent = "Could not load evaluation: " + e.message;
  }
}

/* ---------- start-up ---------- */

loadSavedProfile();
refreshStatus();
loadUpdates();
