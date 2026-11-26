# WHAT_IT_DOES — scarecrow-mcp, exact capabilities

Written 2026-11-26 from the source files in this repo (`server.py`, `README.md`, `test_client.py`) plus coordinator-verified upstream facts (marked "coordinator-verified"). No marketing prose; every list below is exact.

## 1. What this repo is

`scarecrow-mcp` is a Model Context Protocol (MCP) stdio server (FastMCP, server name `scarecrow-consult`) that exposes the ScareCrow consultation brains as two callable MCP tools (`consult`, `list_lanes`). It is a thin HTTP client: every question is sent as an OpenAI-style chat-completions POST to the sunny-scarecrow balancer on Lappy (`http://192.168.0.33:8486/v1/chat/completions`; docker container `sunny-scarecrow` running `balancer.py` (1039 lines) with `lanes.json` — coordinator-verified), which pins a lane BY NAME (`model == lane name`, `balancer.py:981` — coordinator-verified) and fans out to the browser bridge adapter (`:8507` — browser-session brains) and the cloud lanes (nvapi, openrouter). The repo contains exactly three files — `server.py` (the server, name `scarecrow-consult` per `FastMCP("scarecrow-consult")` line 51), `README.md` (install + lane table), `test_client.py` (end-to-end verification) — plus this doc. `balancer.py` and `lanes.json` are NOT in this repo; they live on Lappy inside the balancer container.

## 2. What the MCP server does — tools, exact signatures

The server registers exactly **two tools** and nothing else (no MCP resources, no prompts).

### Tool 1 — `consult`

```
consult(question: str, lane: str = "bridge-chatgpt", max_tokens: int = 6000, retries: int = 4) -> str
```

| Parameter | Type | Default | Notes (from code) |
|---|---|---|---|
| `question` | str | required | Sent as the entire user message; self-contained — the brains have no memory of prior calls. |
| `lane` | str | `"bridge-chatgpt"` | Must be a key of the `LANES` dict (10 valid values, section 4). Anything else returns an error JSON, not an exception. |
| `max_tokens` | int | `6000` | Passed through verbatim in the payload. Docstring: free reasoning upstreams need >= 6000. |
| `retries` | int | `4` | This is the **total number of attempts**, not extra retries (`for i in range(retries)`). Edge case: `retries < 1` never enters the loop, then `attempts[-1]` raises an unhandled `IndexError`. |

Return value: a JSON string (`indent=1`). Three shapes:

1. Unknown lane:
```json
{ "error": "unknown lane '<lane>'", "valid_lanes": ["bridge-chatgpt", "...sorted..."] }
```
2. Success (at least one attempt returned non-empty `choices[0].message.content`):
```json
{ "lane": "<requested lane>", "upstream_model": "<model field echoed by balancer>",
  "attempts": [ { "attempt": 1, "upstream": "...", "finish": "<finish_reason>", "content_len": <n> } ],
  "answer": "<content string>" }
```
3. Exhausted (every attempt empty content or transport error):
```json
{ "lane": "...", "upstream_model": "<upstream of last recorded attempt, null if none>",
  "attempts": [ ... ], "answer": null,
  "error": "all attempts returned empty content — raise max_tokens or retry" }
```
Transport failures record `{"attempt": <n>, "error": "<repr of exception>"}` in `attempts` (no `upstream`/`finish`/`content_len` keys on those entries). The docstring contract: `upstream_model` names the brain that actually answered and must always be reported alongside the answer.

### Tool 2 — `list_lanes`

```
list_lanes() -> str
```
No parameters. Returns a JSON string: `{"default": "bridge-chatgpt", "lanes": {<10 lane-name keys with one-line descriptions>}}` (the `LANES` dict, verbatim).

## 3. What the consultation call does, step by step

Per `_call()` in `server.py` (lines 54–81), exactly:

1. Build the payload once, reused for all attempts:
   ```json
   { "model": "<lane>", "messages": [{"role": "user", "content": "<question>"}], "max_tokens": <max_tokens> }
   ```
   Exactly one user message — no system prompt, no history.
2. `POST http://192.168.0.33:8486/v1/chat/completions` with headers `Authorization: Bearer evo-local` and `Content-Type: application/json`. Body is the payload from step 1 (identical bytes on every attempt — rotation comes from the balancer, not from a changed request).
3. The balancer (docker container `sunny-scarecrow` on Lappy 192.168.0.33, running `balancer.py` (1039 lines) with `lanes.json` — coordinator-verified) resolves `model == lane name` as a direct lane pin, bypassing round-robin (`balancer.py:981` — coordinator-verified).
4. Wait for the full response. HTTP timeout per attempt: **300 s**, hardcoded (no parameter).
5. On exception (timeout, connection refused, malformed JSON — any `Exception`): record `{"attempt": i+1, "error": repr(e)}` in `attempts` and go to the next attempt.
6. On a parsed response: read `r["model"]` (upstream identity echo), `r["choices"][0]["message"]`, its `content`, and `r["choices"][0]["finish_reason"]`; record `{"attempt": i+1, "upstream": ..., "finish": ..., "content_len": len(content) or 0}`.
7. If `content` is non-null and `content.strip()` is non-empty → return the success shape (section 2, shape 2) immediately. Remaining attempts are not used.
8. If content is null/empty → next attempt. **Rotation behavior**: the request body is identical each attempt; the balancer picks a different upstream per call, so a retry lands on a different brain (server docstring + README; coordinator-verified behavior of `balancer.py`).
9. After `retries` attempts with no non-empty content → return the exhausted shape (section 2, shape 3) with `answer: null`.

## 4. Every lane — name, brain, reach, identity evidence

All lanes are reached the same way from this server: `POST http://192.168.0.33:8486/v1/chat/completions` with `"model": "<lane name>"`. The balancer then routes: `bridge-*` lanes go to the bridge adapter at `192.168.0.33:8507` (browser-session brains — coordinator-verified); `nvapi`/`openrouter` are cloud lanes (coordinator-verified); `scarecrow` is round-robin over all lanes, weighted nvapi 100 / openrouter 50 / bridges 10 (coordinator-verified, matching the `LANES` description in `server.py`).

| Lane | Brain | Reach | Identity evidence |
|---|---|---|---|
| `bridge-chatgpt` | GPT-6 (OpenAI, via browser bridge) — **default** consultation brain | balancer → bridge adapter `:8507` | Coordinator-verified test run: canary `SCARECROW-MCP-TEST-OK` returned exactly, first attempt. `upstream_model` echo is the standing identity check per call. |
| `bridge-deepseek` | DeepSeek (via browser bridge) | balancer → bridge adapter `:8507` | Not exercised in the recorded test run; identity = whatever the balancer reports in `upstream_model`. |
| `bridge-mistral` | Mistral (via browser bridge) | balancer → bridge adapter `:8507` | Not exercised in the recorded test run (same standing check). |
| `bridge-qwen` | Qwen (via browser bridge) | balancer → bridge adapter `:8507` | Not exercised in the recorded test run (same standing check). |
| `bridge-gemini` | Gemini (via browser bridge) | balancer → bridge adapter `:8507` | Not exercised in the recorded test run (same standing check). |
| `bridge-grok` | Grok (via bridge) | balancer → bridge adapter `:8507` | Not exercised in the recorded test run (same standing check). |
| `bridge-kimi` | Kimi (via bridge) | balancer → bridge adapter `:8507` | Not exercised in the recorded test run (same standing check). |
| `nvapi` | nemotron-3.5-super-120b (NVIDIA cloud) | balancer → NVIDIA cloud lane | Coordinator-verified test run: canary `NVM-TEST-OK` returned exactly, first attempt. |
| `openrouter` | free rotating pool (`openrouter/free`) | balancer → openrouter cloud lane | Not exercised in the recorded test run (same standing check). |
| `scarecrow` | round-robin over all lanes, weights nvapi 100 / openrouter 50 / bridges 10 | balancer default path | Weight split coordinator-verified; matches the `LANES` string in `server.py` line 48 verbatim: `"round-robin over all lanes (weights: nvapi 100, openrouter 50, bridges 10)"`. Not exercised in the recorded test run. |

Honesty note: `server.py` does not itself verify brain identity — it passes the balancer's `model` field through as `upstream_model`. Pinning is enforced by the balancer (`balancer.py:981`), not by this repo.

## 5. What was tested and what passed

From `test_client.py` (spawns `server.py` over stdio with `C:/Python313/python.exe`, drives it as a real MCP client):

| Test step | What it does | Result (recorded evidence, coordinator-verified) |
|---|---|---|
| 1a | MCP `initialize` handshake, checks `serverInfo.name` present | PASS |
| 1b | `list_tools` returns both `consult` and `list_lanes` | PASS |
| 2 | `call_tool("list_lanes")` output parses as JSON and contains `bridge-chatgpt` | PASS |
| 3 | `consult(question="Reply with exactly: SCARECROW-MCP-TEST-OK", lane="bridge-chatgpt", max_tokens=6000)` | PASS — exact canary token in answer, first attempt |
| 4 | `consult(question="Reply with exactly: NVM-TEST-OK", lane="nvapi", max_tokens=6000)` | PASS — exact canary token in answer, first attempt |

Script exit criteria (from `test_client.py` `main()`): exit 0 iff steps 1–2 all PASS **and** at least one consult returned non-empty content. Both consults exceeded that bar (exact tokens, attempt 1 of the recorded run).

Not covered by the recorded run: the other seven lanes, the retry/rotation path, the unknown-lane error path, the transport-failure path, and the `retries < 1` edge.

## 6. What it does NOT do

Read from the code — actual boundaries, not aspirations:

- **No memory between calls.** Stateless: each `consult` sends exactly one user message and nothing is stored. Follow-up questions get no context; the docstring says so explicitly.
- **No system-prompt support.** The payload is hardcoded to `messages: [{"role": "user", "content": question}]` — there is no parameter, code path, or stored prompt for a system message or multi-turn history.
- **No streaming.** No `stream` field is ever sent; the full JSON response is awaited and parsed with `json.load` in one shot.
- **No GPU use, no local model hosting, no local inference.** `server.py` is a pure-Python stdio HTTP client (`urllib` + `FastMCP`); it runs no model and touches no accelerator. All brains are remote (Lappy balancer → bridge/cloud).
- **No conversation continuation.** Each call is independent; there is no session, thread, or message-store anywhere in the server.
- **Only `max_tokens` is tunable.** No temperature, top_p, stop sequences, tools, response format, or seed parameters exist in the code.
- **Fixed 300 s HTTP timeout per attempt**, hardcoded — no per-call override.
- **`retries` means total attempts**, and `retries < 1` raises an unhandled `IndexError` (`attempts[-1]` on an empty list) — the tool errors instead of returning JSON.
- **No auth beyond the hardcoded key.** Bearer `evo-local` is baked into `server.py`; plain `http://`, no TLS.
- **No identity verification.** The server trusts and echoes the balancer's `model` field; it does not confirm which brain actually answered.
- **Exactly two tools.** No MCP resources, prompts, sampling, or other capabilities are registered. Anything the brains can't do (file access, code execution, memory) this server can't add.
- **Empty-content responses are failures.** Only non-empty `choices[0].message.content` counts; an upstream that burned its whole budget on reasoning returns `answer: null` after all attempts.

## 7. Operational requirements

- **Network**: the host running this server must reach `192.168.0.33:8486` (Lappy, sunny-scarecrow balancer). Bridge lanes additionally depend on the balancer reaching its bridge adapter at `:8507` — not a requirement on this host. No DNS, no TLS.
- **Python**: `C:/Python313/python.exe` (Python 3.13) with the `mcp` package — **1.27.2** present (README, 2026-11-26).
- **Registration** (executed 2026-11-26, user scope):
  ```
  MSYS_NO_PATHCONV=1 claude mcp add --scope user scarecrow -- C:/Python313/python.exe C:/Users/aaron/scarecrow-mcp/server.py
  ```
  The server then runs as a stdio subprocess of the MCP client; it opens no port of its own.
- **Upstream stability**: free reasoning upstreams rotate; keep `max_tokens >= 6000` and expect `retries` to matter (server docstring + README usage notes).
