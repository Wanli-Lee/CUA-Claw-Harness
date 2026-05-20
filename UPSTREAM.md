# Upstream provenance

This repo is forked-by-snapshot from
**[InternLM/WildClawBench](https://github.com/InternLM/WildClawBench)** at commit
`86d7144` (2026-05-20 snapshot).

Renamed to **CUA-Claw-Harness** to make clear that this is a *bridge layer*
that connects the upstream 4 agent harnesses (openclaw / claudecode / codex /
hermesagent) with the **Wanli-Lee/CUA-Claw** (a.k.a. `wildclawbench/`) task
suite of 114 Eyeson_bench tasks.

What's *added* vs upstream:

- **wcb-native task loader** (`src/utils/task_parser.py`): also accepts the
  Eyeson_bench `.md` format (no YAML frontmatter; `## Prompt` / `## Warmup` /
  `## Expected Output` / `## Grader` Python).
- **wcb-native grader runner** (`src/utils/grading.py`): runs the Python
  `def grade(workspace_path, transcript)` block via a `GRADER_RUNNER_TEMPLATE`.
- **GUI MCP server** (`mcp_servers/computer_mcp.py`): exposes `__computer__`
  actions (click/type/screenshot/scroll/...) over stdio MCP, backed by
  `pyautogui` + `scrot` inside `wildclawbench-gui:v0.1` (Xvfb + Xfce).
- **All 4 harnesses receive the MCP wiring** so the same task can be run
  under any backend with identical GUI tool surface.
- **Azure GPT-5.5 as the default model** via the user's LiteLLM endpoint
  (`http://10.160.199.230:4000/v1`).

Nothing in this repo writes back to the user's `wildclawbench/` checkout —
that checkout is referenced read-only via a `tasks_wcb` symlink.
