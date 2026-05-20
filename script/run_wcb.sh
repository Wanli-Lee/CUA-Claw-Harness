#!/usr/bin/env bash
# CUA-Claw-Harness one-key driver.
#
# Usage:
#   bash script/run_wcb.sh codex                 # all 114 tasks, 1 worker, codex
#   bash script/run_wcb.sh codex --parallel 4
#   bash script/run_wcb.sh codex --batch batch1 --category DSK
#   bash script/run_wcb.sh codex --task tasks_wcb/batch1/DSK/DSK_task_0_multimonitor_layout.md
#
# Default endpoints (override via env):
#   WCB_AGENT_BASE_URL   = http://172.17.0.1:4200/v1   (Azure gpt-5.5 via LiteLLM)
#   WCB_AGENT_API_KEY    = sk-litellm-azure-direct
#   WCB_AGENT_MODEL      = gpt-5.5
#   WCB_JUDGE_BASE_URL   = http://172.17.0.1:4141/v1   (cop-api gpt-5.5)
#   WCB_JUDGE_API_KEY    = (empty)
#   WCB_JUDGE_MODEL      = gpt-5.5
set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat <<USAGE
Usage:
  bash script/run_wcb.sh <openclaw|openclaw_gui|claudecode|codex|hermesagent> [extra args]

CLI backends (codex/claudecode/hermesagent/openclaw): per-task subprocess
that talks to the Azure LiteLLM at 4200 and uses 4141 cop-api as judge.

openclaw_gui: GUI backend — boots a full KVM desktop via DesktopEnv and
runs OpenClaw with Xfce. Uses Agent-as-Judge instead of the in-VM grader.
Delegates to script/launchers_aj_gui/run_<model>.sh.

Examples:
  bash script/run_wcb.sh codex                          # 114 task × codex × gpt-5.5
  bash script/run_wcb.sh codex --parallel 4
  bash script/run_wcb.sh claudecode --batch batch1
  bash script/run_wcb.sh hermesagent --task tasks_wcb/batch1/DSK/DSK_task_0_multimonitor_layout.md
  bash script/run_wcb.sh openclaw_gui --task tasks_wcb/batch1/DSK/DSK_task_0_multimonitor_layout.md
USAGE
  exit 1
fi

cd "$(dirname "$0")/.."

# Default endpoints — only set if not already set, so callers can override.
export WCB_AGENT_BASE_URL="${WCB_AGENT_BASE_URL:-http://172.17.0.1:4200/v1}"
export WCB_AGENT_API_KEY="${WCB_AGENT_API_KEY:-sk-litellm-azure-direct}"
export WCB_AGENT_MODEL="${WCB_AGENT_MODEL:-gpt-5.5}"
export WCB_JUDGE_BASE_URL="${WCB_JUDGE_BASE_URL:-http://172.17.0.1:4141/v1}"
export WCB_JUDGE_API_KEY="${WCB_JUDGE_API_KEY:-}"
export WCB_JUDGE_MODEL="${WCB_JUDGE_MODEL:-gpt-5.5}"

# Bypass system clash proxy (the agent container reaches LiteLLM directly
# via docker bridge; the host doesn't need clash for these calls).
export NO_PROXY="172.17.0.1,127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="${NO_PROXY}"

exec python3 eval/run_wcb_batch.py "$@"
