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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Missouri Tiny LLM</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>Missouri Tiny LLM</h1>
        <p>Public Missouri data QA</p>
      </div>
      <div class="status" id="status">Ready</div>
    </header>

    <section class="coverage" id="coverage">
      <span>MAP index</span>
      <strong id="coverage-files">-</strong>
      <span>files</span>
      <strong id="coverage-rows">-</strong>
      <span>rows</span>
      <strong id="coverage-categories">-</strong>
      <span>categories</span>
    </section>

    <section class="workspace">
      <form id="ask-form" class="ask-panel">
        <label for="question">Question</label>
        <textarea id="question" name="question" rows="4" maxlength="500">What was the aggregate MAP expenditure total for TRANSPORTATION?</textarea>
        <div class="controls">
          <button type="submit">Ask</button>
          <button type="button" id="clear">Clear</button>
        </div>
      </form>

      <section class="answer-panel" aria-live="polite">
        <div class="answer-head">
          <h2>Answer</h2>
          <span id="model-pill">fine-tuned adapter</span>
        </div>
        <div id="answer" class="answer">Ask a Missouri public-data question.</div>
        <dl class="meta">
          <div>
            <dt>Source</dt>
            <dd id="source">-</dd>
          </div>
          <div>
            <dt>Context</dt>
            <dd id="context">-</dd>
          </div>
          <div>
            <dt>Score</dt>
            <dd id="score">-</dd>
          </div>
          <div>
            <dt>Note</dt>
            <dd id="note">-</dd>
          </div>
        </dl>
        <div class="suggestions" id="suggestions"></div>
        <div class="evidence" id="evidence" aria-label="Evidence"></div>
        <div class="source-rows" id="source-rows" aria-label="Source row preview"></div>
      </section>
    </section>

    <section class="examples">
      <button type="button" data-question="What can I ask?">Coverage</button>
      <button type="button" data-question="How many rows are in the sanitized MAP expenditure build?">MAP rows</button>
      <button type="button" data-question="How many MAP files did we download and index?">MAP index</button>
      <button type="button" data-question="What are the top expenditure agencies in 2025?">Top agencies</button>
      <button type="button" data-question="What was the aggregate MAP expenditure total for TRANSPORTATION in 2025?">Expenditure lookup</button>
      <button type="button" data-question="How much was paid to CAPITAL MALL JC 1 LLC in 2025?">Vendor lookup</button>
      <button type="button" data-question="What was Kory Hubbard's YTD gross pay in 2026?">Employee pay</button>
      <button type="button" data-question="What tax credit amount was issued to CARTWRIGHT HOLDINGS in 2026?">Tax credit</button>
      <button type="button" data-question="How many licensed hospital beds are in the processed hospital profile source?">Hospital beds</button>
      <button type="button" data-question="What is the home address for Kory Hubbard?">Boundary test</button>
    </section>
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
  background: #f6f7f9;
  color: #18202a;
  font-family: Arial, Helvetica, sans-serif;
}

.shell {
  width: min(1080px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 24px 0;
}

.topbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 0 18px;
  border-bottom: 1px solid #d9dee6;
}

h1, h2, p {
  margin: 0;
}

h1 {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 0;
}

.topbar p {
  margin-top: 6px;
  color: #5d6978;
  font-size: 15px;
}

.status, #model-pill {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  padding: 0 12px;
  border: 1px solid #c9d2dd;
  background: #ffffff;
  border-radius: 8px;
  color: #344154;
  font-size: 14px;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 20px;
  margin-top: 24px;
}

.coverage {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  min-height: 38px;
  border: 1px solid #d9dee6;
  background: #ffffff;
  border-radius: 8px;
  padding: 0 12px;
  color: #5d6978;
}

.coverage strong {
  color: #18202a;
}

.ask-panel, .answer-panel {
  background: #ffffff;
  border: 1px solid #d9dee6;
  border-radius: 8px;
  padding: 18px;
}

label, h2 {
  display: block;
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 10px;
}

textarea {
  width: 100%;
  min-height: 156px;
  resize: vertical;
  border: 1px solid #b9c3cf;
  border-radius: 8px;
  padding: 12px;
  font: inherit;
  line-height: 1.45;
}

textarea:focus {
  border-color: #2864a6;
  outline: 3px solid rgba(40, 100, 166, 0.14);
}

.controls, .examples {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.controls {
  margin-top: 12px;
}

button {
  min-height: 38px;
  border: 1px solid #aeb9c6;
  background: #ffffff;
  color: #18202a;
  border-radius: 8px;
  padding: 0 14px;
  font: inherit;
  cursor: pointer;
}

button[type="submit"] {
  background: #245f97;
  border-color: #245f97;
  color: #ffffff;
}

button:disabled {
  cursor: progress;
  opacity: 0.65;
}

.answer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.answer {
  min-height: 126px;
  border: 1px solid #e0e5ec;
  background: #fbfcfd;
  border-radius: 8px;
  padding: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.meta {
  margin: 14px 0 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.meta div {
  min-width: 0;
  border-top: 1px solid #e5e9ef;
  padding-top: 10px;
}

dt {
  color: #5d6978;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

dd {
  margin: 5px 0 0;
  overflow-wrap: anywhere;
  line-height: 1.35;
}

.examples {
  margin-top: 18px;
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
  margin-top: 14px;
  border-top: 1px solid #e5e9ef;
  padding-top: 12px;
}

.evidence:empty {
  display: none;
}

.evidence h3 {
  margin: 0 0 8px;
  color: #5d6978;
  font-size: 12px;
  letter-spacing: 0;
  text-transform: uppercase;
}

.evidence ul {
  margin: 0;
  padding-left: 18px;
}

.evidence li {
  margin: 6px 0;
  line-height: 1.4;
}

.evidence span {
  color: #5d6978;
}

.source-rows {
  margin-top: 14px;
  border-top: 1px solid #e5e9ef;
  padding-top: 12px;
  overflow-x: auto;
}

.source-rows:empty {
  display: none;
}

.source-rows h3 {
  margin: 0 0 8px;
  color: #5d6978;
  font-size: 12px;
  letter-spacing: 0;
  text-transform: uppercase;
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

@media (max-width: 780px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .meta {
    grid-template-columns: 1fr;
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
const coverageFiles = document.getElementById("coverage-files");
const coverageRows = document.getElementById("coverage-rows");
const coverageCategories = document.getElementById("coverage-categories");

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
  modelPill.textContent = "fine-tuned adapter";

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
    answer.textContent = data.answer || "";
    source.textContent = data.retrieved_source || data.source || "-";
    context.textContent = data.retrieved_context_id || "-";
    score.textContent = data.retrieval_score === undefined ? "-" : data.retrieval_score;
    note.textContent = data.source_note || "-";
    modelPill.textContent = data.synthesis_model || data.model || (data.used_model ? "model" : "public lookup");
    renderSuggestions(data.suggestions || []);
    renderEvidence(data.citations || [], data.dataset_snapshot);
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

function renderEvidence(items, snapshot) {
  evidence.innerHTML = "";
  if (!items.length && !snapshot) return;
  const heading = document.createElement("h3");
  heading.textContent = "Evidence";
  const list = document.createElement("ul");
  items.forEach((item) => {
    const row = document.createElement("li");
    const files = (item.source_files || []).map((file) => {
      const rows = file.row_count === undefined ? "" : ` (${formatNumber(file.row_count)} rows)`;
      return `${file.file_name}${rows}`;
    }).join(", ");
    const scope = item.year || item.year_range || "indexed range";
    const matched = item.matched_rows === undefined || item.matched_rows === null
      ? ""
      : `; matched rows: ${formatNumber(item.matched_rows)}`;
    const title = document.createElement("strong");
    title.textContent = item.category || "Public data";
    const detail = document.createTextNode(`: ${item.kind || item.lookup_table || "lookup"} `);
    const scopeEl = document.createElement("span");
    scopeEl.textContent = `${scope}${matched}`;
    row.appendChild(title);
    row.appendChild(detail);
    row.appendChild(scopeEl);
    if (files) {
      const lineBreak = document.createElement("br");
      const filesEl = document.createElement("span");
      filesEl.textContent = `Files: ${files}`;
      row.appendChild(lineBreak);
      row.appendChild(filesEl);
    }
    list.appendChild(row);
  });
  if (snapshot && snapshot.snapshot_id) {
    const snapshotRow = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = "Dataset snapshot";
    const detail = document.createElement("span");
    detail.textContent = `: ${snapshot.snapshot_id}; ${formatNumber(snapshot.file_rows_total)} parsed MAP rows`;
    snapshotRow.appendChild(title);
    snapshotRow.appendChild(detail);
    list.appendChild(snapshotRow);
  }
  evidence.appendChild(heading);
  evidence.appendChild(list);
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

async function loadCoverage() {
  try {
    const response = await fetch("/api/coverage");
    const data = await response.json();
    const categories = data.categories || [];
    const files = categories.reduce((sum, item) => sum + (item.file_count || 0), 0);
    const rows = categories.reduce((sum, item) => sum + (item.row_count || 0), 0);
    coverageFiles.textContent = files.toLocaleString();
    coverageRows.textContent = rows.toLocaleString();
    coverageCategories.textContent = categories.length.toLocaleString();
  } catch (error) {
    coverageFiles.textContent = "-";
  }
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

loadCoverage();
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
