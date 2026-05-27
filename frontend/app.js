const baseUrlInput = document.getElementById("baseUrl");
const functionalReqInput = document.getElementById("functionalReq");
const nonFunctionalReqInput = document.getElementById("nonFunctionalReq");
const runIdInput = document.getElementById("runId");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const clearBtn = document.getElementById("clearBtn");
const logsEl = document.getElementById("logs");
const connectionBadge = document.getElementById("connectionBadge");
const latestRunIdEl = document.getElementById("latestRunId");
const eventCountEl = document.getElementById("eventCount");

let abortController = null;
let eventCount = 0;
let activeRunId = null;

function setBadge(type, text) {
  connectionBadge.classList.remove("badge-idle", "badge-live", "badge-done", "badge-error");
  connectionBadge.classList.add(type);
  connectionBadge.textContent = text;
}

function appendLog(line) {
  logsEl.textContent += line + "\n";
  logsEl.scrollTop = logsEl.scrollHeight;
}

function appendLogChunk(text) {
  logsEl.textContent += text;
  logsEl.scrollTop = logsEl.scrollHeight;
}

function updateEventCount() {
  eventCountEl.textContent = `${eventCount} events`;
}

function setRunningState(isRunning) {
  startBtn.disabled = isRunning;
  stopBtn.disabled = !isRunning;
}

function parseEventBlock(rawBlock) {
  const lines = rawBlock.split("\n");
  let eventName = "message";
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  return {
    eventName,
    data: dataLines.join("\n"),
  };
}

function defaultRequirements() {
  if (!functionalReqInput.value.trim()) {
    functionalReqInput.value = "User can sign in and upload profile images.";
  }
  if (!nonFunctionalReqInput.value.trim()) {
    nonFunctionalReqInput.value = "Support 1000 concurrent users and limit upload size to 5MB.";
  }
}

async function startStream() {
  defaultRequirements();

  const baseUrlRaw = baseUrlInput.value.trim().replace(/\/$/, "");
  const baseUrl = baseUrlRaw || window.location.origin;
  const payload = {
    functional_req: functionalReqInput.value.trim(),
    non_functional_req: nonFunctionalReqInput.value.trim(),
  };

  const runId = runIdInput.value.trim();
  if (runId) {
    payload.run_id = runId;
  }

  activeRunId = runId || null;

  abortController = new AbortController();
  setRunningState(true);
  setBadge("badge-live", "Streaming");
  appendLog(`[client] connecting to ${baseUrl}/runs/stream`);

  try {
    const response = await fetch(`${baseUrl}/runs/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: abortController.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        if (!block.trim()) {
          continue;
        }

        const event = parseEventBlock(block);
        eventCount += 1;
        updateEventCount();

        if (event.eventName === "log") {
          try {
            const payload = JSON.parse(event.data);
            appendLogChunk(payload.text ?? "");
          } catch (_err) {
            appendLogChunk(event.data);
          }
        } else {
          appendLog(`[${event.eventName}] ${event.data}`);
        }

        if (event.eventName === "status") {
          try {
            const parsed = JSON.parse(event.data);
            if (parsed.run_id) {
              activeRunId = parsed.run_id;
              latestRunIdEl.textContent = parsed.run_id;
              runIdInput.value = parsed.run_id;
            }
          } catch (_err) {
            // status payload parsing failure should not break stream rendering
          }
        }

        if (event.eventName === "done") {
          try {
            const parsed = JSON.parse(event.data);
            if (parsed.run_id) {
              activeRunId = parsed.run_id;
              latestRunIdEl.textContent = parsed.run_id;
              runIdInput.value = parsed.run_id;
            }
          } catch (_err) {
            // done payload parsing failure should not break stream rendering
          }
          setBadge("badge-done", "Completed");
        }

        if (event.eventName === "error") {
          setBadge("badge-error", "Error");
        }
      }
    }

    if (connectionBadge.textContent === "Streaming") {
      setBadge("badge-done", "Completed");
    }
  } catch (err) {
    if (err.name === "AbortError") {
      appendLog("[client] stream stopped by user");
      setBadge("badge-idle", "Stopped");
    } else {
      appendLog(`[client] stream failed: ${err.message}`);
      setBadge("badge-error", "Error");
    }
  } finally {
    setRunningState(false);
    abortController = null;
  }
}

startBtn.addEventListener("click", () => {
  void startStream();
});

stopBtn.addEventListener("click", () => {
  const targetRunId = activeRunId || runIdInput.value.trim();
  if (targetRunId) {
    const baseUrl = baseUrlInput.value.trim().replace(/\/$/, "");
    void fetch(`${baseUrl}/runs/${targetRunId}/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }).catch(() => undefined);
  }

  if (abortController) {
    abortController.abort();
  }
});

clearBtn.addEventListener("click", () => {
  logsEl.textContent = "";
  eventCount = 0;
  updateEventCount();
  activeRunId = null;
});

updateEventCount();
