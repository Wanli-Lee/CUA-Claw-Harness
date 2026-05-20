"""CUA-Claw-Harness — WCB-task driver for the upstream 4 backends.

Walks tasks_wcb/batch{1,2,3,batch_gen}/<CAT>/*.md (114 Eyeson_bench tasks)
and runs each through the user-selected backend (openclaw / claudecode /
codex / hermesagent), reusing all upstream run_batch.py infrastructure
(parsing, container management, grading, summary). The only thing this
file changes is **task discovery**: instead of TASKS_DIR/<CAT>/*.md it
expands to TASKS_DIR/<BATCH>/<CAT>/*task_*.md.

Usage:
    python eval/run_wcb_batch.py codex
    python eval/run_wcb_batch.py codex --parallel 4
    python eval/run_wcb_batch.py codex --batch batch1 --category DSK
    python eval/run_wcb_batch.py codex --task tasks_wcb/batch1/DSK/DSK_task_0_multimonitor_layout.md
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.claudecode import ClaudeCodeAgent
from src.agents.codex import CodexAgent
from src.agents.openclaw import OpenClawAgent
from src.utils.task_parser import parse_task_md
from src.utils.endpoint_utils import (
    normalize_openrouter_base_url_for_claudecode,
    normalize_openrouter_base_url_for_openclaw,
    wcb_agent_endpoint,
)
from src.utils.grading import print_summary, print_global_summary
from eval.run_batch import run_single_task, load_models_config

logger = logging.getLogger("run_wcb_batch")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

ROOT_DIR = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT_DIR / os.environ.get("TASKS_SUBDIR", "tasks_wcb")
OUTPUT_DIR = ROOT_DIR / os.environ.get("OUTPUT_SUBDIR", "output")

ALL_BATCHES = ["batch1", "batch2", "batch3", "batch_gen"]
ALL_CATEGORIES = ["WEB", "DAV", "OPS", "DOC", "DES", "GAM", "SPA", "DSK"]


def discover_wcb_tasks(
    batches: list[str], categories: list[str], task_filter: str | None,
) -> list[dict]:
    tasks: list[dict] = []
    for b in batches:
        bdir = TASKS_DIR / b
        if not bdir.is_dir():
            logger.warning("batch dir missing: %s", bdir)
            continue
        for c in categories:
            cdir = bdir / c
            if not cdir.is_dir():
                continue
            for md in sorted(cdir.glob("*task_*.md")):
                if ".bak" in md.name:
                    continue
                if task_filter and task_filter not in md.name:
                    continue
                try:
                    t = parse_task_md(md)
                    t["category"] = f"{b}_{c}"  # so output_dir is unique per batch
                    t["wcb_batch"] = b
                    t["wcb_native_category"] = c
                    tasks.append(t)
                except Exception as exc:
                    logger.warning("parse failed for %s: %s", md, exc)
    return tasks


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("backend",
                    choices=["openclaw", "openclaw_gui",
                             "claudecode", "codex", "hermesagent"])
    ap.add_argument("--task", default=None,
                    help="Path to a single .md to run (skips batch/category iteration).")
    ap.add_argument("--batch", default="all",
                    help=f"Comma-separated batch list, or 'all' (default). Options: {ALL_BATCHES}")
    ap.add_argument("--category", default="all",
                    help=f"Comma-separated category list, or 'all' (default). Options: {ALL_CATEGORIES}")
    ap.add_argument("--task-filter", default=None,
                    help="Substring filter applied to task .md filename.")
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--model", default=None,
                    help="LLM model name; defaults to WCB_AGENT_MODEL or gpt-5.5.")
    ap.add_argument("--thinking", default=None)
    ap.add_argument("--models-config", default=None)
    ap.add_argument("--openclaw-image-model", default=None)
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve endpoint + default model
    agent_base_url, agent_api_key, default_model = wcb_agent_endpoint()
    model = args.model or default_model
    args.model = model  # so downstream sees the resolved value

    # openclaw_gui doesn't fit the BaseAgent/run_single_task mold — it spawns
    # its own multi-VM AJ pipeline via the launcher script. Dispatch early.
    if args.backend == "openclaw_gui":
        from src.agents.openclaw_gui.runner import drive_openclaw_gui
        rc = drive_openclaw_gui(args)
        sys.exit(rc)

    # Construct backend (CLI backends + legacy openclaw)
    backend_name = args.backend
    if backend_name == "openclaw":
        backend = OpenClawAgent(
            gateway_port=int(os.environ.get("GATEWAY_PORT", "18789")),
            openrouter_api_key=agent_api_key,
            openrouter_base_url=normalize_openrouter_base_url_for_openclaw(agent_base_url),
            image_model=args.openclaw_image_model,
        )
    elif backend_name == "codex":
        # Both 4200 LiteLLM (Azure gpt-5.5) and 4141 cop-api expose
        # /v1/responses for gpt-5.5, so codex can use either. Per user
        # spec (CUA-Claw-Harness 2026-05-20), agent for all 3 harnesses
        # goes to 4200 Azure. Override with WCB_CODEX_BASE_URL if needed.
        codex_base = os.environ.get("WCB_CODEX_BASE_URL", agent_base_url)
        codex_key = os.environ.get("WCB_CODEX_API_KEY", agent_api_key)
        logger.info("Codex backend endpoint: %s", codex_base)
        backend = CodexAgent(
            openrouter_api_key=codex_key,
            openrouter_base_url=normalize_openrouter_base_url_for_openclaw(codex_base),
        )
    elif backend_name == "claudecode":
        backend = ClaudeCodeAgent(
            anthropic_api_key=agent_api_key,
            openrouter_base_url=normalize_openrouter_base_url_for_claudecode(agent_base_url),
        )
    elif backend_name == "hermesagent":
        from src.agents.hermesagent import HermesAgentAgent
        backend = HermesAgentAgent(
            openrouter_api_key=agent_api_key,
            openrouter_base_url=normalize_openrouter_base_url_for_openclaw(agent_base_url),
        )
    else:
        raise SystemExit(f"unknown backend: {backend_name}")

    output_root = OUTPUT_DIR / backend_name

    models_config = None
    if args.models_config:
        models_config = load_models_config(Path(args.models_config).expanduser().resolve())

    if args.task:
        tasks = [parse_task_md(Path(args.task))]
    else:
        batches = ALL_BATCHES if args.batch == "all" else [b.strip() for b in args.batch.split(",")]
        cats    = ALL_CATEGORIES if args.category == "all" else [c.strip() for c in args.category.split(",")]
        tasks = discover_wcb_tasks(batches, cats, args.task_filter)

    logger.info("WCB driver: backend=%s, model=%s, base_url=%s, tasks=%d, parallel=%d",
                backend_name, model, agent_base_url, len(tasks), args.parallel)
    logger.info("Output root: %s", output_root)

    if not tasks:
        logger.error("No tasks matched filter — exiting")
        sys.exit(1)

    all_results: list[dict] = []
    safe_model = re.sub(r'[^a-zA-Z0-9.\-_]', '_', model)
    if args.parallel <= 1:
        for t in tasks:
            r = run_single_task(t, model, backend, output_root,
                                models_config=models_config, thinking=args.thinking)
            all_results.append(r)
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(run_single_task, t, model, backend, output_root,
                                   None, args.thinking, models_config): t["task_id"]
                       for t in tasks}
            for fut in as_completed(futures):
                try:
                    all_results.append(fut.result())
                except Exception as exc:
                    tid = futures[fut]
                    logger.error("[%s] thread exc: %s", tid, exc)
                    all_results.append({"task_id": tid, "scores": {}, "error": str(exc)})

    # Per-batch summaries + global
    by_batch: dict[str, list[dict]] = {}
    for r in all_results:
        # Recover batch from task_id (run_single_task uses short prefix)
        # We stamped category=<batch>_<CAT>, so output_dir reflects that;
        # for summary we just lump everything into a global summary.
        by_batch.setdefault("all", []).append(r)
    for label, rs in by_batch.items():
        print_summary(rs, label, output_root, safe_model)
    print_global_summary(all_results, output_root, safe_model)


if __name__ == "__main__":
    main()
