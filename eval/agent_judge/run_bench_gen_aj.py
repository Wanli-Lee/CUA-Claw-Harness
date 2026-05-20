"""Drop-in launcher: same CLI as eval/run_bench_gen.py but uses Agent-as-Judge.

Usage::

    python eval/agent_judge/run_bench_gen_aj.py \\
        --provider_name docker --headless --mode gui \\
        --model gpt-5.4 --litellm_base_url http://10.160.199.230:4000/v1 \\
        --bench_subdirs Eyeson_batch1,Eyeson_batch2,Eyeson_batch3,Eyeson_batch_gen \\
        --categories WEB,DAV,OPS,DOC,DES,GAM,SPA,DSK \\
        --result_dir /tmp/results_test_aj

Mechanism: imports `eval.run_bench_gen` (the standard launcher) but FIRST
monkey-patches `eval.run_deep_search_in_osworld.run_one` to point to our
`run_one_aj` (skips grader, runs Agent-as-Judge after VM teardown).

Original eval/run_bench_gen.py and eval/run_deep_search_in_osworld.py are
NEVER modified — only their function references are swapped at import time.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Import the targets to be patched.
import eval.run_deep_search_in_osworld as ds  # noqa: E402
from eval.agent_judge.run_one_aj import run_one_aj  # noqa: E402

# Save the original (in case downstream code wants to fall back) and patch.
ds._original_run_one = ds.run_one
ds.run_one = run_one_aj

# Now trigger the standard run_bench_gen.main(); it will use our patched run_one.
import eval.run_bench_gen as rbg  # noqa: E402

if __name__ == "__main__":
    rbg.main()
