"""Local web UI for asking the Missouri Tiny LLM adapter."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

from missouri_tiny_llm.ask_model import AskEngine, DEFAULT_ADAPTER, DEFAULT_MODEL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Missouri Public Data Chat</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <img class="state-mark" src="/assets/mo-capitol-mark.png" alt="" aria-hidden="true">
        <div>
          <h1>Missouri Public Data Chat</h1>
        </div>
      </div>
      <div class="status" id="status" aria-live="polite">Ready</div>
    </header>

    <section class="workspace">
      <form id="ask-form" class="ask-panel">
        <label for="question">Your question</label>
        <textarea id="question" name="question" rows="4" maxlength="500">Who is the governor of Missouri?</textarea>
        <div class="controls">
          <button type="submit">Ask</button>
          <button type="button" id="clear">Clear</button>
        </div>
        <div class="examples-block">
          <h2>Examples</h2>
          <div class="examples">
            <button type="button" data-question="How much did TRANSPORTATION pay BOKF NA in 2025?">Vendor payment</button>
            <button type="button" data-question="What was Kory Hubbard's YTD gross pay in 2026?">Employee pay</button>
            <button type="button" data-question="What tax credit amount was issued to CARTWRIGHT HOLDINGS in 2026?">Tax credit</button>
            <button type="button" data-question="Who is the governor of Missouri?">Governor</button>
          </div>
        </div>
      </form>

      <section class="answer-panel" aria-live="polite">
        <h2>Answer</h2>
        <span id="model-pill">grounded local synthesis</span>
        <div id="answer" class="answer">Mike Kehoe is the governor of Missouri.</div>
        <section class="source-section">
          <h3>Source</h3>
          <div id="source"><a href="https://governor.mo.gov/" target="_blank" rel="noopener noreferrer">https://governor.mo.gov/</a></div>
        </section>
        <div class="suggestions" id="suggestions"></div>
        <div class="evidence" id="evidence" aria-label="Evidence">
          <h3>Evidence</h3>
          <table>
            <tr>
              <th>Source</th>
              <th>Type</th>
              <th>Verified</th>
            </tr>
            <tr>
              <td>Official Missouri Governor site</td>
              <td>Civic fact</td>
              <td>2026-05-23</td>
            </tr>
          </table>
        </div>
        <div class="source-rows" id="source-rows" aria-label="Source row preview"></div>
        <span id="context" hidden>-</span>
        <span id="score" hidden>-</span>
        <span id="note" hidden>-</span>
      </section>
    </section>

    <footer class="footer">
      <div class="disclaimer">
        <span class="warning-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path d="M12 3l10 18H2z"></path>
            <path d="M12 9v5"></path>
            <path d="M12 17.5h.01"></path>
          </svg>
        </span>
        <span>Independent case study. Not endorsed by the State of Missouri.</span>
      </div>
      <section class="data-sources" aria-label="Public data sources">
        <h2>Data sources</h2>
        <div class="source-links">
          <a href="https://mapyourtaxes.mo.gov/MAP/Portal/Default.aspx" target="_blank" rel="noopener noreferrer">MAP</a>
          <a href="https://missouribuys.mo.gov/contractboard" target="_blank" rel="noopener noreferrer">MissouriBUYS</a>
          <a href="https://archive.oa.mo.gov/purch/contracts/" target="_blank" rel="noopener noreferrer">OA contracts</a>
          <a href="https://data.mo.gov/data.json" target="_blank" rel="noopener noreferrer">data.mo.gov</a>
          <a href="https://governor.mo.gov/" target="_blank" rel="noopener noreferrer">Governor</a>
          <a href="https://dese.mo.gov/school-data" target="_blank" rel="noopener noreferrer">DESE</a>
          <a href="https://health.mo.gov/data/" target="_blank" rel="noopener noreferrer">DHSS</a>
          <a href="https://www.mshp.dps.mo.gov/MSHPWeb/SAC/data_960grid.html" target="_blank" rel="noopener noreferrer">MSHP</a>
          <a href="https://meric.mo.gov/data/economic/local-area-unemployment-statistics/laus" target="_blank" rel="noopener noreferrer">MERIC</a>
          <a href="https://dnr.mo.gov/data-e-services" target="_blank" rel="noopener noreferrer">DNR</a>
          <a href="https://www.msdis.missouri.edu/" target="_blank" rel="noopener noreferrer">MSDIS</a>
          <a href="https://www.modot.org/modatazone/traffic" target="_blank" rel="noopener noreferrer">MoDOT</a>
          <a href="https://auditor.mo.gov/AuditReport/Menu" target="_blank" rel="noopener noreferrer">Auditor</a>
          <a href="https://dor.mo.gov/public-reports/" target="_blank" rel="noopener noreferrer">DOR</a>
          <a href="https://mec.mo.gov/" target="_blank" rel="noopener noreferrer">MEC</a>
          <a href="https://www.sos.mo.gov/elections/s_default" target="_blank" rel="noopener noreferrer">SOS elections</a>
          <a href="https://oa.mo.gov/budget-and-planning" target="_blank" rel="noopener noreferrer">OA Budget</a>
          <a href="https://dese.mo.gov/childhood/child-care/child-care-data-dashboards" target="_blank" rel="noopener noreferrer">Child care</a>
          <a href="https://health.mo.gov/safety/nursinghomesinspected/index.php" target="_blank" rel="noopener noreferrer">LTC inspections</a>
          <a href="https://psc.mo.gov/General/PSC_Reports" target="_blank" rel="noopener noreferrer">PSC</a>
          <a href="https://health.mo.gov/safety/cannabis/" target="_blank" rel="noopener noreferrer">Cannabis</a>
          <a href="https://agmarketnews.mo.gov/reports/" target="_blank" rel="noopener noreferrer">Agriculture</a>
        </div>
      </section>
    </footer>
  </main>
  <script src="/app.js"></script>
</body>
</html>
"""

CSS = """* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #080808;
  color: #05070a;
  font-family: Arial, Helvetica, sans-serif;
}

.shell {
  width: min(1006px, 100vw);
  min-height: 668px;
  margin: 0 auto;
  background: #ffffff;
  border: 1px solid #cfd5de;
  border-radius: 8px;
  overflow: hidden;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 77px;
  padding: 14px 27px 10px;
  border-bottom: 3px solid #b8860b;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.state-mark {
  flex: 0 0 auto;
  width: 55px;
  height: 52px;
  object-fit: contain;
}

h1, h2, p {
  margin: 0;
}

h1 {
  font-size: 31px;
  font-weight: 700;
  letter-spacing: 0;
}

.status {
  position: absolute;
  width: 1px;
  height: 1px;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  overflow: hidden;
  white-space: nowrap;
}

.warning-icon svg {
  display: block;
  width: 100%;
  height: 100%;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 44%) minmax(0, 56%);
  min-height: 488px;
}

.ask-panel, .answer-panel {
  min-width: 0;
  background: #ffffff;
  border: 0;
  border-radius: 0;
}

.ask-panel {
  padding: 22px 24px 28px;
}

.answer-panel {
  padding: 22px 29px 28px 34px;
}

.ask-panel {
  border-right: 1px solid #cfd5de;
}

label, h2 {
  display: block;
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 12px;
}

textarea {
  width: 100%;
  min-height: 203px;
  resize: vertical;
  border: 1px solid #8f9aaa;
  border-radius: 6px;
  padding: 14px 12px;
  font: inherit;
  font-size: 14px;
  line-height: 1.45;
}

textarea:focus {
  border-color: #2864a6;
  outline: 3px solid rgba(40, 100, 166, 0.14);
}

.controls, .examples {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.controls {
  margin-top: 16px;
}

button {
  min-height: 36px;
  border: 1px solid #aeb9c6;
  background: #ffffff;
  color: #05070a;
  border-radius: 6px;
  padding: 0 16px;
  font: inherit;
  cursor: pointer;
}

button[type="submit"] {
  min-width: 92px;
  min-height: 42px;
  background: #075de8;
  border-color: #075de8;
  color: #ffffff;
  font-size: 16px;
  font-weight: 700;
}

#clear {
  min-width: 76px;
  min-height: 42px;
}

button:disabled {
  cursor: progress;
  opacity: 0.65;
}

#model-pill {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  margin-bottom: 21px;
  padding: 0 10px;
  border: 1px solid #c6cdd6;
  background: #f9fafb;
  border-radius: 8px;
  color: #1e2936;
  font-size: 14px;
}

.answer {
  min-height: 71px;
  padding: 0 0 26px;
  border-bottom: 1px solid #cfd5de;
  font-size: 18px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.source-section {
  padding: 24px 0 28px;
  border-bottom: 1px solid #cfd5de;
}

.source-section h3,
.evidence h3,
.source-rows h3,
.examples-block h2 {
  margin: 0 0 14px;
  color: #05070a;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0;
}

#source {
  min-height: 28px;
  font-size: 18px;
  overflow-wrap: anywhere;
}

#source:empty::before {
  content: "-";
}

a {
  color: #004ee8;
  text-decoration: underline;
  text-underline-offset: 2px;
}

a:hover {
  color: #183f66;
}

.examples-block {
  margin-top: 24px;
}

.examples {
  gap: 9px;
}

.examples button {
  min-height: 32px;
  padding: 0 7px;
  color: #004ee8;
  font-size: 13px;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.suggestions:empty {
  display: none;
}

.suggestions button {
  font-size: 13px;
  min-height: 34px;
}

.evidence {
  padding-top: 22px;
}

.evidence:empty {
  display: none;
}

.evidence table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  border: 1px solid #c9d0db;
  border-radius: 7px;
  overflow: hidden;
  font-size: 14px;
}

.evidence th,
.evidence td {
  padding: 12px 13px;
  border-right: 1px solid #c9d0db;
  border-bottom: 1px solid #c9d0db;
  text-align: left;
  vertical-align: top;
}

.evidence th:last-child,
.evidence td:last-child {
  border-right: 0;
}

.evidence tr:last-child td {
  border-bottom: 0;
}

.evidence th {
  background: #f8f9fb;
  font-weight: 700;
}

.source-rows {
  display: none;
}

.source-rows:empty {
  display: none;
}

.source-rows table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.source-rows th,
.source-rows td {
  border-top: 1px solid #e5e9ef;
  padding: 7px 8px;
  text-align: left;
  vertical-align: top;
}

.source-rows th {
  color: #5d6978;
  font-weight: 700;
}

.footer {
  min-height: 102px;
  display: grid;
  grid-template-columns: minmax(0, 38%) minmax(0, 62%);
  align-items: center;
  gap: 22px;
  padding: 14px 24px;
  border-top: 2px solid #c18a0a;
  background: #fffaf0;
  color: #111827;
  font-size: 14px;
}

.disclaimer {
  display: flex;
  align-items: center;
  gap: 16px;
}

.warning-icon {
  flex: 0 0 auto;
  color: #c18a0a;
  width: 25px;
  height: 25px;
  line-height: 1;
}

.data-sources {
  display: grid;
  gap: 8px;
}

.data-sources h2 {
  margin: 0;
  font-size: 13px;
  line-height: 1;
  text-transform: uppercase;
  color: #4b5563;
}

.source-links {
  display: flex;
  flex-wrap: wrap;
  gap: 7px 10px;
}

.source-links a {
  color: #004ee8;
  font-size: 13px;
  line-height: 1.2;
}

@media (max-width: 780px) {
  .shell {
    border-radius: 0;
  }

  .workspace {
    grid-template-columns: 1fr;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .footer {
    grid-template-columns: 1fr;
  }

  .ask-panel {
    border-right: 0;
    border-bottom: 1px solid #cfd5de;
  }
}
"""

JS = """const form = document.getElementById("ask-form");
const question = document.getElementById("question");
const answer = document.getElementById("answer");
const source = document.getElementById("source");
const context = document.getElementById("context");
const score = document.getElementById("score");
const note = document.getElementById("note");
const statusEl = document.getElementById("status");
const modelPill = document.getElementById("model-pill");
const clearButton = document.getElementById("clear");
const suggestions = document.getElementById("suggestions");
const evidence = document.getElementById("evidence");
const sourceRows = document.getElementById("source-rows");

function appendLinkedText(parent, text) {
  const value = String(text || "");
  const urlPattern = /(https?:\/\/[^\s]+)/g;
  let lastIndex = 0;
  let match;
  while ((match = urlPattern.exec(value)) !== null) {
    if (match.index > lastIndex) {
      parent.appendChild(document.createTextNode(value.slice(lastIndex, match.index)));
    }
    const rawUrl = match[0];
    const trailing = rawUrl.match(/[),.;:!?]+$/)?.[0] || "";
    const href = trailing ? rawUrl.slice(0, -trailing.length) : rawUrl;
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = href;
    parent.appendChild(link);
    if (trailing) {
      parent.appendChild(document.createTextNode(trailing));
    }
    lastIndex = match.index + rawUrl.length;
  }
  if (lastIndex < value.length) {
    parent.appendChild(document.createTextNode(value.slice(lastIndex)));
  }
}

function setLinkedText(element, text) {
  element.innerHTML = "";
  appendLinkedText(element, text);
}

function firstPublicSourceFile(citations) {
  for (const item of citations || []) {
    for (const file of item.source_files || []) {
      if (/^https?:\/\//.test(file.file_name || "")) {
        return file;
      }
    }
  }
  for (const item of citations || []) {
    if ((item.source_files || []).length) return item.source_files[0];
  }
  return null;
}

function sourceDisplayName(file, citation) {
  const url = file?.file_name || "";
  if (url.includes("governor.mo.gov")) return "Official Missouri Governor site";
  if (url.includes("missouribuys.mo.gov")) return "MissouriBUYS Contract Board";
  if (url.includes("archive.oa.mo.gov/purch")) return "Office of Administration Contract Search";
  return file?.category_label || citation?.category || file?.file_name || "Public source";
}

function evidenceType(item, file) {
  const kind = String(item.kind || item.lookup_table || "");
  const url = String(file?.file_name || "");
  if (kind.includes("governor")) return "Civic fact";
  if (kind.includes("contract") || url.includes("/purch/")) return "Contract metadata";
  if (kind.includes("employee")) return "Employee pay";
  if (kind.includes("expenditure")) return "MAP expenditure";
  return item.category || "Public data";
}

function verifiedLabel(data, item) {
  const context = String(data?.retrieved_context_id || "");
  const dateMatch = context.match(/20\d{2}-\d{2}-\d{2}/);
  if (dateMatch) return dateMatch[0];
  if (item.year) return String(item.year);
  if (item.year_range) return String(item.year_range);
  return "Indexed source";
}

function renderSource(data) {
  source.innerHTML = "";
  const file = firstPublicSourceFile(data.citations || []);
  if (file && /^https?:\/\//.test(file.file_name || "")) {
    const link = document.createElement("a");
    link.href = file.file_name;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = file.file_name;
    source.appendChild(link);
    return;
  }
  if (file?.file_name) {
    source.textContent = file.file_name;
    return;
  }
  source.textContent = data.retrieved_source || data.source || "-";
}

function setBusy(isBusy) {
  statusEl.textContent = isBusy ? "Working" : "Ready";
  form.querySelectorAll("button, textarea").forEach((el) => {
    el.disabled = isBusy;
  });
}

async function askModel(text) {
  setBusy(true);
  answer.textContent = "Generating...";
  source.textContent = "-";
  context.textContent = "-";
  score.textContent = "-";
  note.textContent = "-";
  suggestions.innerHTML = "";
  evidence.innerHTML = "";
  sourceRows.innerHTML = "";
  modelPill.textContent = "grounded local synthesis";

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Request failed");
    }
    setLinkedText(answer, data.answer || "");
    renderSource(data);
    context.textContent = data.retrieved_context_id || "-";
    score.textContent = data.retrieval_score === undefined ? "-" : data.retrieval_score;
    setLinkedText(note, data.source_note || "-");
    modelPill.textContent = data.synthesis_model ? "grounded local synthesis" : (data.model || "public lookup");
    renderSuggestions(data.suggestions || []);
    renderEvidence(data.citations || [], data.dataset_snapshot, data);
    renderSourceRows(data.source_rows || []);
  } catch (error) {
    answer.textContent = error.message;
    modelPill.textContent = "error";
  } finally {
    setBusy(false);
  }
}

function renderSuggestions(items) {
  suggestions.innerHTML = "";
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    if (typeof item === "string") {
      button.textContent = item;
      button.addEventListener("click", () => {
        question.value = item;
        askModel(item);
      });
    } else {
      const label = [item.label, item.year, item.amount].filter(Boolean).join(" | ");
      button.textContent = label;
    }
    suggestions.appendChild(button);
  });
}

function formatNumber(value) {
  return value === undefined || value === null ? "-" : Number(value).toLocaleString();
}

function renderEvidence(items, snapshot, data) {
  evidence.innerHTML = "";
  if (!items.length && !snapshot) return;
  const heading = document.createElement("h3");
  heading.textContent = "Evidence";
  const table = document.createElement("table");
  const header = document.createElement("tr");
  ["Source", "Type", "Verified"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    header.appendChild(th);
  });
  table.appendChild(header);
  items.forEach((item) => {
    const file = firstPublicSourceFile([item]) || (item.source_files || [])[0] || {};
    const row = document.createElement("tr");
    const sourceCell = document.createElement("td");
    sourceCell.textContent = sourceDisplayName(file, item);
    const typeCell = document.createElement("td");
    typeCell.textContent = evidenceType(item, file);
    const verifiedCell = document.createElement("td");
    verifiedCell.textContent = verifiedLabel(data, item);
    row.appendChild(sourceCell);
    row.appendChild(typeCell);
    row.appendChild(verifiedCell);
    table.appendChild(row);
  });
  if (!items.length && snapshot && snapshot.snapshot_id) {
    const row = document.createElement("tr");
    ["Dataset snapshot", "MAP index", snapshot.snapshot_id].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = value;
      row.appendChild(td);
    });
    table.appendChild(row);
  }
  evidence.appendChild(heading);
  evidence.appendChild(table);
}

function renderSourceRows(items) {
  sourceRows.innerHTML = "";
  if (!items.length) return;
  const heading = document.createElement("h3");
  heading.textContent = `Source Row Preview (${items.length})`;
  const table = document.createElement("table");
  const keys = [];
  items.forEach((item) => {
    Object.keys(item.values || {}).forEach((key) => {
      if (!keys.includes(key)) keys.push(key);
    });
  });
  const header = document.createElement("tr");
  ["File", "Row", ...keys].forEach((key) => {
    const th = document.createElement("th");
    th.textContent = key;
    header.appendChild(th);
  });
  table.appendChild(header);
  items.forEach((item) => {
    const tr = document.createElement("tr");
    [item.source_file || "-", item.source_row_number || "-", ...keys.map((key) => (item.values || {})[key] || "")].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.appendChild(td);
    });
    table.appendChild(tr);
  });
  sourceRows.appendChild(heading);
  sourceRows.appendChild(table);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = question.value.trim();
  if (text) askModel(text);
});

clearButton.addEventListener("click", () => {
  question.value = "";
  answer.textContent = "";
  source.textContent = "-";
  context.textContent = "-";
  score.textContent = "-";
  note.textContent = "-";
  suggestions.innerHTML = "";
  evidence.innerHTML = "";
  sourceRows.innerHTML = "";
  question.focus();
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    question.value = button.dataset.question;
    askModel(button.dataset.question);
  });
});
"""


class MissouriTinyHandler(BaseHTTPRequestHandler):
    engine: AskEngine

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_text(self, body: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_text(json.dumps(payload, indent=2), "application/json; charset=utf-8", status)

    def retrieval_path(self, result: dict[str, Any]) -> str:
        model = result.get("model")
        if result.get("synthesis_model"):
            return "grounded_llm_synthesis"
        if model in {"deterministic_public_lookup", "capability_summary"}:
            return "deterministic_lookup"
        if model == "retrieved_public_qa":
            return "retrieved_qa"
        if model == "public_data_boundary":
            return "boundary_refusal"
        if model in {"unsupported_scope_guardrail", "retrieval_guardrail"}:
            return "unsupported"
        return "unknown"

    def response_envelope(self, result: dict[str, Any], request_id: str) -> dict[str, Any]:
        payload = dict(result)
        payload.setdefault("citations", [])
        payload["request_id"] = request_id
        payload["served_at_utc"] = utc_now()
        payload["dataset_snapshot"] = self.engine.map_index.snapshot()
        payload["retrieval_path"] = self.retrieval_path(payload)
        return payload

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self.send_text(HTML, "text/html; charset=utf-8")
            return
        if self.path == "/styles.css":
            self.send_text(CSS, "text/css; charset=utf-8")
            return
        if self.path == "/app.js":
            self.send_text(JS, "application/javascript; charset=utf-8")
            return
        if self.path == "/assets/mo-capitol-mark.png":
            asset_path = ASSETS_DIR / "mo-capitol-mark.png"
            if asset_path.exists():
                self.send_bytes(asset_path.read_bytes(), "image/png")
                return
            self.send_json({"error": "Asset not found"}, HTTPStatus.NOT_FOUND)
            return
        if self.path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "model": self.engine.model_id,
                    "synthesis_mode": self.engine.synthesis_mode,
                    "dataset_snapshot": self.engine.map_index.snapshot(),
                }
            )
            return
        if self.path == "/api/coverage":
            coverage = self.engine.map_index.coverage()
            coverage["dataset_snapshot"] = self.engine.map_index.snapshot()
            self.send_json(coverage)
            return
        self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/ask":
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        request_id = uuid4().hex[:12]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                self.send_json({"error": "Question is too large", "request_id": request_id}, HTTPStatus.BAD_REQUEST)
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            question = str(payload.get("question", "")).strip()
            if not question:
                self.send_json({"error": "Question is required", "request_id": request_id}, HTTPStatus.BAD_REQUEST)
                return
            result = self.engine.ask(question)
            self.send_json(self.response_envelope(result, request_id))
        except Exception as exc:
            print(f"request_id={request_id} error={exc}")
            self.send_json(
                {"error": "Internal server error", "request_id": request_id, "served_at_utc": utc_now()},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )


def serve(
    host: str,
    port: int,
    max_new_tokens: int,
    model_id: str,
    adapter_path: Path,
    use_base: bool,
    synthesis_mode: str,
    synthesis_max_new_tokens: int,
) -> None:
    MissouriTinyHandler.engine = AskEngine(
        model_id=model_id,
        adapter_path=adapter_path,
        use_base=use_base,
        max_new_tokens=max_new_tokens,
        synthesis_mode=synthesis_mode,
        synthesis_max_new_tokens=synthesis_max_new_tokens,
    )
    server = ThreadingHTTPServer((host, port), MissouriTinyHandler)
    print(f"Missouri Tiny LLM UI listening on http://{host}:{port}")
    print(f"Answer synthesis: {synthesis_mode}; model: {model_id}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--model-id", default=DEFAULT_MODEL)
    parser.add_argument("--adapter-path", default=str(DEFAULT_ADAPTER.relative_to(PROJECT_ROOT)))
    parser.add_argument("--base", action="store_true")
    parser.add_argument("--synthesis", choices=["off", "local"], default="off")
    parser.add_argument("--synthesis-max-new-tokens", type=int, default=160)
    args = parser.parse_args()
    if args.max_new_tokens < 1 or args.max_new_tokens > 96:
        raise SystemExit("--max-new-tokens must be between 1 and 96")
    if args.synthesis_max_new_tokens < 16 or args.synthesis_max_new_tokens > 256:
        raise SystemExit("--synthesis-max-new-tokens must be between 16 and 256")
    serve(
        args.host,
        args.port,
        args.max_new_tokens,
        args.model_id,
        PROJECT_ROOT / args.adapter_path,
        args.base,
        args.synthesis,
        args.synthesis_max_new_tokens,
    )


if __name__ == "__main__":
    main()
