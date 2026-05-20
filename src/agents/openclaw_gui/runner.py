"""openclaw_gui driver — translate eval/run_wcb_batch.py CLI flags into
the AJ-GUI launcher invocation.

This intentionally does NOT implement BaseAgent.run_task — the AJ-GUI
pipeline (eval/agent_judge/run_bench_gen_aj.py) is its own multi-process
runner that drives N parallel KVM VMs through ds.discover_tasks() and
ds.run_one_aj(). Wrapping it in BaseAgent would require re-implementing
that orchestration; instead we hand the whole thing to the launcher
script and let it write into <repo>/output/openclaw_gui/...

Usage from run_wcb_batch.py:

    drive_openclaw_gui(args)

Args is the argparse.Namespace built by run_wcb_batch.parse_args(); we
read .task / .batch / .category / .task_filter / .parallel / .model and
build the equivalent BENCH_SUBDIRS / CATEGORIES / TASK_FILTER /
NUM_ENVS env that the launcher script consumes.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("openclaw_gui")

REPO_ROOT = Path(__file__).resolve().parents[3]
LAUNCHER_SH = REPO_ROOT / "script" / "launchers_aj_gui" / "run_gpt_5_5.sh"

# Map model name → launcher script (we only ship gpt-5.5 today). Add
# more entries as we copy/adapt run_<model>.sh from upstream.
MODEL_LAUNCHER = {
    "gpt-5.5": "run_gpt_5_5.sh",
}


def _resolve_launcher(model: str) -> Path:
    name = MODEL_LAUNCHER.get(model)
    if not name:
        # Fallback: assume same naming convention as upstream
        # (run_<model_underscored>.sh) — easier to add models without
        # editing this dict.
        safe = re.sub(r"[^a-zA-Z0-9]", "_", model)
        guess = REPO_ROOT / "script" / "launchers_aj_gui" / f"run_{safe}.sh"
        if guess.exists():
            return guess
        raise SystemExit(
            f"openclaw_gui: no launcher for model={model!r} "
            f"(expected at {guess})"
        )
    return REPO_ROOT / "script" / "launchers_aj_gui" / name


def _task_path_to_filters(task_md: Path) -> dict:
    """tasks_wcb/batch1/DSK/DSK_task_0_multimonitor_layout.md →
    {BENCH_SUBDIRS: 'Eyeson_batch1', CATEGORIES: 'DSK',
     TASK_FILTER: 'DSK_task_0_multimonitor_layout'}
    """
    p = task_md.resolve()
    parts = p.parts
    # Find the batch dir token (batch1/2/3/batch_gen)
    batch_dir = None
    for i, seg in enumerate(parts):
        if seg.startswith("batch"):
            batch_dir = seg
            cat = parts[i + 1] if i + 1 < len(parts) else None
            break
    if not batch_dir:
        raise SystemExit(f"openclaw_gui: can't infer batch from {task_md}")
    bench_subdir_map = {
        "batch1": "Eyeson_batch1",
        "batch2": "Eyeson_batch2",
        "batch3": "Eyeson_batch3",
        "batch_gen": "Eyeson_batch_gen",
    }
    bench_sub = bench_subdir_map.get(batch_dir, batch_dir)
    task_id = task_md.stem  # filename without .md
    return {
        "BENCH_SUBDIRS": bench_sub,
        "CATEGORIES": cat or "WEB,DAV,OPS,DOC,DES,GAM,SPA,DSK",
        "TASK_FILTER": task_id,
    }


def drive_openclaw_gui(args) -> int:
    """Translate args → env → exec launcher. Returns exit code."""
    launcher = _resolve_launcher(args.model or "gpt-5.5")
    env = os.environ.copy()
    env["NUM_ENVS"] = str(max(1, args.parallel))
    if args.thinking:
        env["AJ_THINKING"] = args.thinking

    if args.task:
        filters = _task_path_to_filters(Path(args.task))
        env.update({k: str(v) for k, v in filters.items()})
    else:
        # Batch / category iteration: translate to underlying naming.
        if args.batch and args.batch != "all":
            batches = [b.strip() for b in args.batch.split(",") if b.strip()]
            env["BENCH_SUBDIRS"] = ",".join(
                {"batch1": "Eyeson_batch1",
                 "batch2": "Eyeson_batch2",
                 "batch3": "Eyeson_batch3",
                 "batch_gen": "Eyeson_batch_gen"}.get(b, b) for b in batches
            )
        if args.category and args.category != "all":
            env["CATEGORIES"] = args.category
        if args.task_filter:
            env["TASK_FILTER"] = args.task_filter

    # Default RESULT_ROOT_BASE lives under repo/output/openclaw_gui (set in
    # the launcher); allow user to override via env.
    logger.info("openclaw_gui: handing off to %s", launcher)
    logger.info("openclaw_gui: BENCH_SUBDIRS=%s  CATEGORIES=%s  TASK_FILTER=%s  NUM_ENVS=%s",
                env.get("BENCH_SUBDIRS"),
                env.get("CATEGORIES"),
                env.get("TASK_FILTER"),
                env.get("NUM_ENVS"))

    rc = subprocess.call(["bash", str(launcher)], env=env)
    return rc
