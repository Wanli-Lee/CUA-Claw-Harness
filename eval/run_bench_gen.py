"""Run the NIPS2026/bench_gen* tasks (default WEB) inside OSWorld VMs.

Identical pipeline to ``run_wanli_fix.py`` except for two differences:

  • ``ds.DEEP_SEARCH_SUBDIR`` is monkey-patched to ``"bench_gen"`` by
    default, or to ``--bench_subdir`` when provided;
    the symlink ``wildclawbench/wen_tasks/bench_gen ->
    ../../NIPS2026/bench_gen`` makes ``discover_tasks`` find
    ``<wcb_root>/wen_tasks/<bench_subdir>/<CAT>/*.md`` and matching
    ``<wcb_root>/wen_tasks/<bench_subdir>/workspace/<CAT>/<dir>``.
  • ``--categories`` defaults to ``WEB`` (only domain currently built).

Usage::

    python eval/run_bench_gen.py                          # all WEB cases, gui mode
    python eval/run_bench_gen.py --task_filter task_1     # only WEB-01
    python eval/run_bench_gen.py --mode gui               # gui only
    python eval/run_bench_gen.py --num_envs 1
    python eval/run_bench_gen.py --dry-run                # parse + grader smoke only
    python eval/run_bench_gen.py --bench_subdir bench_gen_based \
      --categories WEB,EDU,OPS,DES,GAM,DOC,SPA,DSK --dry-run

``--dry-run`` does NOT spin up DesktopEnv. It only:

  • discovers tasks under bench_gen/<CAT>/*.md
  • parses each task .md
  • exec()s the ``grade()`` function on an empty results dir
  • prints discovery + parse + grader return codes

It is used to smoke-test newly built cases without needing LiteLLM /
Docker / KasmVNC running.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from multiprocessing import Manager, Process
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import eval.run_deep_search_in_osworld as ds  # noqa: E402

# Redirect to NIPS2026/bench_gen via wen_tasks/bench_gen symlink.
ds.DEEP_SEARCH_SUBDIR = "bench_gen"

logger = logging.getLogger("run_bench_gen")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


# ---------------------------------------------------------------------------
# Real-time worker (verbatim copy of run_wanli_fix._real_time_worker so we do
# not import it — keeping run_bench_gen.py self-contained).
# ---------------------------------------------------------------------------
def _real_time_worker(env_idx, task_queue, args, shared, progress):
    from multiprocessing import current_process
    name = current_process().name
    base_result_root = Path(args.result_dir)
    wcb_root = Path(args.wcb_root)
    ds._import_wcb(wcb_root)

    from desktop_env.desktop_env import DesktopEnv
    from mm_agents.openclaw_agent import OpenClawAgent

    # Stagger startup to avoid 10 envs racing the port-allocation lock and
    # IO-thrashing the qcow2 base image at the same time.
    stagger_s = float(getattr(args, "startup_stagger_s", 6.0)) * env_idx
    if stagger_s > 0:
        time.sleep(stagger_s)

    while True:
        try:
            task, mode = task_queue.get(timeout=5)
        except Exception:
            break
        if mode not in ("cli", "gui"):
            continue
        # If task carries its own bench_subdir (multi-batch global pool), nest
        # results under it so all batches share a single RESULT_ROOT without
        # collisions. Otherwise (legacy single-batch run), use base_result_root
        # as-is so existing layouts stay unchanged.
        sub = task.get("bench_subdir")
        result_root = (base_result_root / sub) if sub else base_result_root
        if ds.already_done(task, mode, args.model, result_root):
            progress.append({"event": "skip", "name": name,
                             "task": task["task_id"], "mode": mode})
            continue
        out_dir = result_root / mode / args.model / task["category"] / task["task_id"]
        progress.append({"event": "start", "name": name,
                         "task": task["task_id"], "mode": mode,
                         "ts": time.time()})
        env = None
        try:
            env = DesktopEnv(
                provider_name=args.provider_name,
                region=args.region,
                path_to_vm=args.path_to_vm,
                action_space="pyautogui",
                screen_size=(args.screen_width, args.screen_height),
                headless=args.headless,
                os_type=args.os_type,
                require_a11y_tree=False,
                require_terminal=True,
                client_password=args.client_password,
            )
            agent = OpenClawAgent(
                model=args.model,
                litellm_base_url=args.litellm_base_url,
                litellm_api_key=args.litellm_api_key,
                client_password=args.client_password,
                timeout=3600,  # WCB 2026-05-14: 1h hard cap per task to prevent multi-hour worker hangs
                gui=(mode == "gui"),
                max_steps=task.get("max_steps") or args.max_steps,
                cua_native=bool(args.cua_native),
            )
            rec = ds.run_one(env, agent, task, mode, out_dir, wcb_root,
                             http_proxy=args.http_proxy)
            shared.append({
                "category": task["category"],
                "task_id": task["task_id"],
                "mode": mode,
                "score": rec.get("score", 0.0),
                "scores": rec.get("scores"),
                "error": rec.get("error"),
                "elapsed_seconds": rec.get("elapsed_seconds"),
            })
            progress.append({"event": "done", "name": name,
                             "task": task["task_id"], "mode": mode,
                             "score": rec.get("score", 0.0),
                             "error": rec.get("error"),
                             "ts": time.time()})
        except Exception as exc:
            import traceback
            progress.append({"event": "crash", "name": name,
                             "task": task["task_id"], "mode": mode,
                             "error": str(exc)[-300:],
                             "ts": time.time()})
            logger.error("[%s] %s/%s [%s] crashed: %s\n%s",
                         name, task["category"], task["task_id"], mode,
                         exc, traceback.format_exc())
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass


def _monitor(progress, total, stop_after):
    seen_idx = 0
    finished = 0
    t0 = time.time()
    while finished < total and (time.time() - t0) < stop_after:
        time.sleep(2)
        cur_len = len(progress)
        for i in range(seen_idx, cur_len):
            ev = progress[i]
            kind = ev["event"]
            tag = f"[{ev['name']}][{ev['mode']}] {ev['task']}"
            if kind == "start":
                logger.info("▶ START  %s", tag)
            elif kind == "skip":
                logger.info("⊘ SKIP   %s (already done)", tag)
                finished += 1
            elif kind == "done":
                err = ev.get("error")
                if err:
                    logger.warning("✗ DONE   %s score=%.3f err=%s",
                                   tag, ev.get("score", 0.0), str(err)[:120])
                else:
                    logger.info("✓ DONE   %s score=%.3f",
                                tag, ev.get("score", 0.0))
                finished += 1
            elif kind == "crash":
                logger.error("☠ CRASH  %s err=%s", tag, ev.get("error"))
                finished += 1
        seen_idx = cur_len
    logger.info("monitor exit: finished=%d/%d, elapsed=%.0fs",
                finished, total, time.time() - t0)


# ---------------------------------------------------------------------------
# Dry-run path: parse + grader smoke without DesktopEnv / LiteLLM.
# ---------------------------------------------------------------------------
def _dry_run(tasks):
    """Smoke-test newly built cases by importing the grade() from each task .md
    and running it against an empty workspace. Just verifies the case files are
    parseable and the grader doesn't crash."""
    logger.info("=== DRY RUN: parsing %d tasks ===", len(tasks))
    ok = 0
    for t in tasks:
        tid = f"{t['category']}/{t['task_id']}"
        md = Path(t["file_path"])
        ws = Path(t["workspace_path"])
        # Confirm exec/ exists and is non-empty (.gitkeep counts).
        exec_dir = ws / "exec"
        if not exec_dir.exists():
            logger.error("✗ %s  workspace exec/ missing: %s", tid, exec_dir)
            continue
        # Extract grade() body from the task .md and exec it in a tmp module.
        text = md.read_text(encoding="utf-8")
        if "def grade(" not in text:
            logger.error("✗ %s  no grade() in %s", tid, md)
            continue
        # naive code-fence extraction
        lines = text.splitlines()
        in_block = False
        code = []
        for line in lines:
            if line.strip().startswith("```python"):
                in_block = True
                continue
            if in_block and line.strip().startswith("```"):
                break
            if in_block:
                code.append(line)
        src = "\n".join(code)
        # Run grader against empty /tmp workspace mock
        with tempfile.TemporaryDirectory() as td:
            tw = Path(td) / "tmp_workspace"
            (tw / "results").mkdir(parents=True, exist_ok=True)
            try:
                # provide a minimal _judge_helper stub so grader doesn't crash
                stub = Path(td) / "_judge_helper.py"
                stub.write_text(
                    "def vlm_score_rubric(*a, **kw):\n"
                    "    return {'judge_method': 'stub'}\n",
                    encoding="utf-8",
                )
                sys.path.insert(0, str(td))
                # patch /tmp_workspace by chdir + monkeypatching Path defaults?
                # Graders use absolute /tmp_workspace/... — symlink it:
                tw_abs = Path("/tmp_workspace_dryrun")
                if tw_abs.is_symlink() or tw_abs.exists():
                    if tw_abs.is_symlink():
                        tw_abs.unlink()
                # cannot symlink under /, fall back: textual replace
                src2 = src.replace('/tmp_workspace', str(tw))
                ns = {}
                exec(compile(src2, str(md), "exec"), ns)
                grade_fn = ns["grade"]
                res = grade_fn(workspace_path=str(ws))
                score = res.get("overall_score", res.get("score"))
                logger.info("✓ %s  parses + grades on empty=%.3f",
                            tid, score if score is not None else -1)
                ok += 1
            except Exception as exc:
                logger.error("✗ %s  grader crashed: %s", tid, exc)
            finally:
                sys.path.pop(0)
    logger.info("=== DRY RUN: %d/%d OK ===", ok, len(tasks))
    return ok == len(tasks)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Run NIPS2026/bench_gen tasks (WEB by default).")
    ap.add_argument("--provider_name", default="docker")
    ap.add_argument("--region", default=None)
    ap.add_argument("--path_to_vm", default=None)
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--screen_width", type=int, default=1920)
    ap.add_argument("--screen_height", type=int, default=1080)
    ap.add_argument("--os_type", default="Ubuntu")
    ap.add_argument("--client_password", default="password")
    ap.add_argument("--num_envs", type=int, default=1)

    ap.add_argument("--model", default="gpt-5.4")
    ap.add_argument("--litellm_base_url", default=os.environ.get(
        "WCB_LITELLM_BASE_URL", "http://172.29.0.1:4000/v1"))
    ap.add_argument("--litellm_api_key", default=os.environ.get(
        "WCB_LITELLM_KEY", "sk-litellm-local"))
    ap.add_argument("--max_steps", type=int, default=200)

    ap.add_argument("--wcb_root", default=str(ROOT))
    ap.add_argument("--bench_subdir", default="bench_gen",
                    help="Subdir under wildclawbench/wen_tasks/ (default bench_gen). Ignored if --bench_subdirs is set.")
    ap.add_argument("--bench_subdirs", default=None,
                    help="CSV of bench subdirs to merge into one global task pool "
                         "(e.g. 'Eyeson_batch1,Eyeson_batch2,Eyeson_batch3,Eyeson_batch_gen'). "
                         "When set, all batches share workers / queue, results "
                         "go to <result_dir>/<bench_subdir>/<mode>/<model>/...")
    ap.add_argument("--categories", default="WEB",
                    help="CSV of categories under the selected bench subdir (default WEB).")
    ap.add_argument("--task_filter", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--mode", choices=["cli", "gui", "both"], default="gui")
    ap.add_argument("--cua_native", type=int, choices=[0, 1], default=0,
                    help=("0 (default): register __computer__ as a normal "
                          "function tool — image and __computer__ screenshots "
                          "all flow to the model. 1: use OpenAI native "
                          "computer_use_preview tool; image/read images get "
                          "stripped from model context. See "
                          "NIPS2026/codex_2026_04_videos/cua_vs_image_channel.md."))
    ap.add_argument("--result_dir", default="./results_bench_gen")
    ap.add_argument("--http_proxy", default=os.environ.get("WCB_VM_HTTP_PROXY", ""))
    ap.add_argument("--monitor_max_seconds", type=int, default=86400)
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="Parse tasks + run grader on empty results, no VM.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    wcb_root = Path(args.wcb_root).resolve()

    # Multi-batch mode: merge tasks from several bench_subdirs into one global
    # pool so workers stay busy across batch boundaries (no batch-level barrier).
    if args.bench_subdirs:
        subdirs = [s.strip() for s in args.bench_subdirs.split(",") if s.strip()]
        tasks = []
        for sub in subdirs:
            ds.DEEP_SEARCH_SUBDIR = sub
            sub_tasks = ds.discover_tasks(wcb_root, cats)
            for t in sub_tasks:
                t["bench_subdir"] = sub
            tasks.extend(sub_tasks)
            logger.info("  [%s] discovered %d tasks", sub, len(sub_tasks))
    else:
        ds.DEEP_SEARCH_SUBDIR = args.bench_subdir
        tasks = ds.discover_tasks(wcb_root, cats)
    if args.task_filter:
        # Support comma-separated list of substrings.
        filters = [f.strip() for f in args.task_filter.split(",") if f.strip()]
        tasks = [t for t in tasks if any(f in t["task_id"] for f in filters)]
    if args.limit:
        tasks = tasks[:args.limit]

    if not tasks:
        logger.error("No tasks discovered under %s/wen_tasks/%s/{%s}",
                     wcb_root, args.bench_subdir, ",".join(cats))
        return

    logger.info("=" * 70)
    logger.info("bench_gen runner — %d tasks", len(tasks))
    for t in tasks:
        logger.info("  • %s/%s   (workspace=%s)",
                    t["category"], t["task_id"], t["workspace_path"])
    logger.info("=" * 70)

    if args.dry_run:
        ok = _dry_run(tasks)
        sys.exit(0 if ok else 1)

    modes = ["cli", "gui"] if args.mode == "both" else [args.mode]
    total_runs = len(tasks) * len(modes)
    logger.info("modes=%s  total_runs=%d  cua_native=%d", modes, total_runs, args.cua_native)
    logger.info("Result dir: %s", Path(args.result_dir).resolve())

    if "cli" in modes:
        logger.warning("=" * 70)
        logger.warning("DEPRECATION: --mode cli on run_bench_gen.py uses the FULL DesktopEnv")
        logger.warning("(KVM + Ubuntu Xfce desktop, just sets gui=False on the agent). The")
        logger.warning("agent CAN still cheat by spawning Xvfb / pyautogui inside the VM.")
        logger.warning("For a TRUE no-desktop CLI ablation, use:")
        logger.warning("  • run_bench_gen_lite.py            (OpenAI /responses transport)")
        logger.warning("  • run_bench_gen_lite_messages.py   (Anthropic /v1/messages transport)")
        logger.warning("Both wrap DockerLiteEnv (no X server). The eval/launchers_*/_common.sh")
        logger.warning("dispatchers auto-route MODE=cli to the lite runner — prefer those.")
        logger.warning("=" * 70)

    mgr = Manager()
    queue = mgr.Queue()
    shared = mgr.list()
    progress = mgr.list()
    for t in tasks:
        for m in modes:
            queue.put((t, m))

    procs = [Process(target=_real_time_worker,
                     args=(i, queue, args, shared, progress),
                     name=f"env-{i+1}") for i in range(args.num_envs)]
    for p in procs:
        p.start()
    _monitor(progress, total_runs, args.monitor_max_seconds)
    for p in procs:
        p.join(timeout=10)

    # Summary
    out = Path(args.result_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / f"summary_{datetime.now():%Y%m%d_%H%M%S}.json"
    summary_path.write_text(json.dumps(list(shared), indent=2, ensure_ascii=False),
                            encoding="utf-8")
    logger.info("Summary written: %s", summary_path)


if __name__ == "__main__":
    main()
