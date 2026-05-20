#!/usr/bin/env bash
# AJ-GUI gpt-5.5 entry point (CUA-Claw-Harness).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
launch_model "gpt-5.5" "agent_judge/run_bench_gen_aj.py" "${RESULT_TAG:-AJ_GUI_$(date +%Y%m%d)}" "$@"
