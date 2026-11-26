# scarecrow-mcp

> **Ten brains, one tool call.** GPT-6, DeepSeek, Mistral, Qwen, Gemini, Grok, Kimi and
> nemotron — consulted natively from any Claude session, pinned by lane name, with the
> answering brain named in every response.

An MCP stdio server that turns the **ScareCrow consultation tier** — a round-robin model
balancer running on the fleet's GPU box — into a first-class tool. What used to require
hand-rolled `curl` incantations and round-robin luck is now `consult(question, lane)`.

---

## Why this exists

The balancer on Lappy (`sunny-scarecrow`, `balancer.py`, 1039 lines) accepts any model
name and routes it across upstream lanes — but its default round-robin is
**nvapi-weighted 100/50/10**, so asking for `chatgpt` usually landed on nemotron and
looked like the brains were lying about who they were. Reading the balancer source
revealed the actual contract (`balancer.py:981`):

> **direct-name access: model == a lane name → THAT lane only.**

Pin the lane, get the brain. This server exists so nobody has to read 1,039 lines of
balancer source to learn that again.

```
 Claude session ──MCP──> scarecrow-consult ──HTTP──> sunny-scarecrow :8486 (Lappy)
                                              balancer.py:981 lane pinning
                                                    ├── bridge-chatgpt  ──> GPT-6      (browser bridge :8507)
                                                    ├── bridge-deepseek ──> DeepSeek   (browser bridge)
                                                    ├── bridge-mistral  ──> Mistral    (browser bridge)
                                                    ├── bridge-qwen     ──> Qwen       (browser bridge)
                                                    ├── bridge-gemini   ──> Gemini     (browser bridge)
                                                    ├── bridge-grok     ──> Grok       (browser bridge)
                                                    ├── bridge-kimi     ──> Kimi       (browser bridge)
                                                    ├── nvapi           ──> nemotron-3.5-super-120b (NVIDIA cloud)
                                                    └── openrouter      ──> free rotating pool
```

---

## Quick start

```json
// .claude.json (user scope — registered already on this machine, 2026-11-26)
"scarecrow": {
  "command": "C:/Python313/python.exe",
  "args": ["C:/Users/aaron/scarecrow-mcp/server.py"]
}
```

Then in any session:

```
consult(question="Review this protocol section for fake-pass vectors...",
        lane="bridge-chatgpt")
```

Real exchange, recorded 2026-11-26 (lane `bridge-chatgpt`, upstream `chatgpt`):

> **Q:** What are you?
> **A:** I am **GPT-6**, a large language model created and developed by **OpenAI** [...]

---

## Tools

### `consult(question, lane="bridge-chatgpt", max_tokens=6000, retries=4)`

Ask a brain a question. Returns JSON:

```json
{
  "lane": "bridge-chatgpt",
  "upstream_model": "chatgpt",
  "attempts": [{"attempt": 1, "upstream": "chatgpt", "finish": "stop", "content_len": 4257}],
  "answer": "..."
}
```

**`upstream_model` names the brain that actually answered. Always report it.** The
balancer rotates free reasoning upstreams per call — a null-content response means the
budget was burned on hidden reasoning, and the server automatically retries onto a
different brain.

### `list_lanes()`

The live lane catalog with descriptions.

---

## Lanes

| Lane | Brain | Path | Notes |
|---|---|---|---|
| `bridge-chatgpt` | **GPT-6** (OpenAI) | browser bridge :8507 | default consultation brain |
| `bridge-deepseek` | DeepSeek | browser bridge | |
| `bridge-mistral` | Mistral | browser bridge | |
| `bridge-qwen` | Qwen | browser bridge | |
| `bridge-gemini` | Gemini | browser bridge | |
| `bridge-grok` | Grok | browser bridge | |
| `bridge-kimi` | Kimi | browser bridge | |
| `nvapi` | nemotron-3.5-super-120b | NVIDIA cloud | strongest local-analysis lane |
| `openrouter` | free rotating pool | OpenRouter | widest variety, least predictable |
| `scarecrow` | round-robin over all | — | nvapi-weighted 100/50/10 |

---

## Operations

- **Endpoint:** `http://192.168.0.33:8486/v1/chat/completions` (Lappy) — auth `Bearer evo-local`
- **Budgets:** free reasoning upstreams burn tokens on hidden reasoning — keep
  `max_tokens >= 6000` and trust the retry rotation
- **Determinism:** none — the balancer rotates; pin a lane when the specific brain matters
- **Precision:** the brains are cloud/browser calls; nothing local is loaded
- **Requires:** Python 3.13 · `mcp` 1.27.2 · network reach to Lappy :8486

## Install

```bash
MSYS_NO_PATHCONV=1 claude mcp add --scope user scarecrow -- \
  C:/Python313/python.exe C:/Users/aaron/scarecrow-mcp/server.py
```

## Verification

`test_client.py` runs the full end-to-end suite over stdio: MCP handshake, tool
listing, and two live consults (bridge-chatgpt + nvapi) asserting exact canary
responses. Record run: **PASS, all steps green, both consults landed first attempt** —
`bridge-chatgpt → upstream "chatgpt"`, `nvapi → upstream "private/nvidia/nemotron-3.5-super-120b-a12b"`.

## Honest limits

- **No memory between calls** — every consult is stateless; pass full context.
- **No streaming** — answers arrive whole.
- **The brains can be wrong** — this tool transports answers; triage is your job.
  (One recorded consultation returned a plausible-sounding failure mode whose core
  claim was wrong on analysis. Triage before accepting.)
- **The balancer is shared fleet infrastructure** — it serves every lane that asks.

---

*Built 2026-11-26 by the nnfs lane, owner-directed. The discovery that makes it work —
lane-name pinning — came from reading `balancer.py` instead of trusting the alias.*
