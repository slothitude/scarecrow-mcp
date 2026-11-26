"""TEST-MCP lane client — end-to-end verification of scarecrow-consult (server.py).

Spawns the server over stdio, does the MCP initialize handshake, lists tools,
calls list_lanes, then calls consult twice (bridge-chatgpt + nvapi).

Exit code 0 iff steps 1-2 PASS and at least one consult returned non-empty content.
"""

import json
import sys
import time
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "C:/Users/aaron/scarecrow-mcp/server.py"
PYTHON = "C:/Python313/python.exe"

results = []  # (step, name, ok, detail)
upstream_models = []


def record(step, name, ok, detail=""):
    results.append((step, name, ok, detail))
    print(f"[step {step}] {'PASS' if ok else 'FAIL'} — {name}" + (f" :: {detail}" if detail else ""))
    return ok


async def run():
    params = StdioServerParameters(command=PYTHON, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            # --- Step 1: initialize handshake + list tools ---
            t0 = time.time()
            init = await session.initialize()
            init_ok = bool(init and init.serverInfo and init.serverInfo.name)
            record("1a", "initialize handshake", init_ok,
                   f"server={init.serverInfo.name} version={init.serverInfo.version}" if init_ok else repr(init))

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            tools_ok = "consult" in names and "list_lanes" in names
            record("1b", "list_tools has consult + list_lanes", tools_ok, f"tools={names}")

            # --- Step 2: list_lanes ---
            res = await session.call_tool("list_lanes", {})
            text = "\n".join(c.text for c in res.content if getattr(c, "text", None))
            try:
                lanes = json.loads(text)
                step2_ok = "bridge-chatgpt" in lanes.get("lanes", {})
                record(2, "list_lanes parses + contains bridge-chatgpt", step2_ok,
                       f"default={lanes.get('default')} lanes={sorted(lanes.get('lanes', {}))}")
            except Exception as e:
                step2_ok = False
                record(2, "list_lanes parses + contains bridge-chatgpt", False, f"json error: {e!r} raw={text[:200]!r}")

            # --- Step 3: consult via bridge-chatgpt ---
            r3 = await session.call_tool("consult", {
                "question": "Reply with exactly: SCARECROW-MCP-TEST-OK",
                "lane": "bridge-chatgpt", "max_tokens": 6000})
            text3 = "\n".join(c.text for c in r3.content if getattr(c, "text", None))
            answer3 = None
            try:
                j3 = json.loads(text3)
                upstream3 = j3.get("upstream_model")
                answer3 = j3.get("answer")
                upstream_models.append(("bridge-chatgpt", upstream3, j3.get("attempts")))
                token_hit = bool(answer3) and "SCARECROW-MCP-TEST-OK" in answer3
                if token_hit:
                    record(3, "consult(bridge-chatgpt)", True,
                           f"upstream={upstream3} TOKEN EXACT MATCH attempts={len(j3.get('attempts', []))}")
                elif answer3 and str(answer3).strip():
                    record(3, "consult(bridge-chatgpt)", True,
                           f"upstream={upstream3} non-empty answer (token not exact): {str(answer3)[:200]!r}")
                else:
                    record(3, "consult(bridge-chatgpt)", False,
                           f"empty/null answer upstream={upstream3} err={j3.get('error')} attempts={j3.get('attempts')}")
            except Exception as e:
                record(3, "consult(bridge-chatgpt)", False, f"json error: {e!r} raw={text3[:200]!r}")

            # --- Step 4: consult via nvapi ---
            j4, answer4 = {}, None
            r4 = await session.call_tool("consult", {
                "question": "Reply with exactly: NVM-TEST-OK",
                "lane": "nvapi", "max_tokens": 6000})
            text4 = "\n".join(c.text for c in r4.content if getattr(c, "text", None))
            try:
                j4 = json.loads(text4)
                upstream4 = j4.get("upstream_model")
                answer4 = j4.get("answer")
                upstream_models.append(("nvapi", upstream4, j4.get("attempts")))
                token_hit4 = bool(answer4) and "NVM-TEST-OK" in answer4
                if token_hit4:
                    record(4, "consult(nvapi)", True,
                           f"upstream={upstream4} TOKEN EXACT MATCH attempts={len(j4.get('attempts', []))}")
                elif answer4 and str(answer4).strip():
                    record(4, "consult(nvapi)", True,
                           f"upstream={upstream4} non-empty answer (token not exact): {str(answer4)[:200]!r}")
                else:
                    record(4, "consult(nvapi)", False,
                           f"empty/null answer upstream={upstream4} err={j4.get('error')} attempts={j4.get('attempts')}")
            except Exception as e:
                record(4, "consult(nvapi)", False, f"json error: {e!r} raw={text4[:200]!r}")

            return step2_ok, answer3, answer4


def main():
    t_start = time.time()
    step2_ok = False
    any_consult_ok = False
    try:
        import asyncio
        step2_ok, answer3, answer4 = asyncio.run(run())
        any_consult_ok = bool((answer3 and str(answer3).strip()) or (answer4 and str(answer4).strip()))
    except Exception:
        print("FATAL during run:")
        traceback.print_exc()

    wall = time.time() - t_start
    print("\n==== SUMMARY ====")
    for step, name, ok, detail in results:
        print(f"  step {step}: {'PASS' if ok else 'FAIL'} — {name}" + (f" :: {detail}" if detail else ""))
    print(f"  upstream models observed: {[(l, m) for l, m, _ in upstream_models]}")
    print(f"  wall time: {wall:.1f}s")

    s1 = all(ok for s, _, ok, _ in results if str(s).startswith("1"))
    verdict = s1 and step2_ok and any_consult_ok
    print(f"  EXIT: {'PASS' if verdict else 'FAIL'} (steps 1-2 {'ok' if s1 and step2_ok else 'NOT ok'}, "
          f"non-empty consult={'yes' if any_consult_ok else 'no'})")
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
