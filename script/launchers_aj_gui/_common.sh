#!/usr/bin/env bash
# CUA-Claw-Harness — AJ-GUI launchers (adapted from
# wildclawbench/eval/launchers_aj_gui_azure/_common.sh).
#
# Backend stack:
#   agent rollout: full DesktopEnv (KVM Xfce) — GUI mode
#   model gateway: local LiteLLM at 0.0.0.0:4200 → Azure direct (gpt-5.5 ...)
#   judge:         OpenClaw multi-turn agent → cop-api gpt-5.5 (4141) by default
#
# Result layout:
#   ${RESULT_ROOT_BASE}/<MODEL>/<RESULT_TAG>/<bench>/gui/<MODEL>/<CAT>/<TASK>/

LAUNCHER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(cd "${LAUNCHER_DIR}/.." && pwd)"
WCB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"     # CUA-Claw-Harness root

# Local LiteLLM proxy fronting Azure direct.
# Host: 127.0.0.1:4200 ; in-VM/docker: 172.17.0.1:4200
LITELLM_PORT="${LITELLM_PORT:-4200}"
LITELLM_HOST_IP="${LITELLM_HOST_IP:-127.0.0.1}"
LITELLM_VM_IP="${LITELLM_VM_IP:-172.17.0.1}"
LITELLM_API_KEY="${LITELLM_API_KEY:-sk-litellm-azure-direct}"
LITELLM_PRECHECK_MODEL="${LITELLM_PRECHECK_MODEL:-gpt-5.5}"

# Judge backend — per user spec 2026-05-20, judge → cop-api 4141 (no key).
JUDGE_HOST_IP="${JUDGE_HOST_IP:-127.0.0.1}"
JUDGE_VM_IP="${JUDGE_VM_IP:-172.17.0.1}"
JUDGE_PORT="${JUDGE_PORT:-4141}"
JUDGE_BASE_URL="${JUDGE_BASE_URL:-http://${JUDGE_HOST_IP}:${JUDGE_PORT}/v1}"
JUDGE_BASE_URL_VM="${JUDGE_BASE_URL_VM:-http://${JUDGE_VM_IP}:${JUDGE_PORT}/v1}"
JUDGE_API_KEY="${JUDGE_API_KEY:-}"
JUDGE_MODEL="${JUDGE_MODEL:-gpt-5.5}"

# Agent-as-Judge runtime config (consumed by run_one_aj.py / judge_runner.py).
export AJ_TIMEOUT="${AJ_TIMEOUT:-1800}"
export AJ_THINKING="${AJ_THINKING:-medium}"
export AJ_OPENCLAW_BIN="${AJ_OPENCLAW_BIN:-${HOME}/judge_agent_test/node_modules/.bin/openclaw}"
export AJ_OPENCLAW_PROFILE="${AJ_OPENCLAW_PROFILE:-azure_judge}"
export AJ_JUDGE_WORKSPACE="${AJ_JUDGE_WORKSPACE:-${HOME}/judge_agent_test/azure_judge_workspace}"
export AJ_TEMPLATE_PROFILE="${AJ_TEMPLATE_PROFILE:-${HOME}/judge_agent_test/template_profile_azure}"
export AJ_TEMPLATE_WORKSPACE="${AJ_TEMPLATE_WORKSPACE:-${HOME}/judge_agent_test/template_workspace_azure}"

# Where to find the 114 Eyeson_bench tasks (data stays in wildclawbench/).
# Override with AJ_BENCH_ROOT to point elsewhere.
export AJ_BENCH_ROOT="${AJ_BENCH_ROOT:-/mnt/nas_nfs/home/wanli/wen/SimpAgent/GUI-KV/OSWorld/wildclawbench/Eyeson_bench}"

# Python interpreter (pre-installed conda env with all DesktopEnv deps).
PY_BIN="${PY_BIN:-/mnt/nas_nfs/home/wanli/conda_envs/gui0_nas/bin/python}"

NUM_ENVS="${NUM_ENVS:-10}"
MODE="${MODE:-gui}"
CATEGORIES="${CATEGORIES:-WEB,DAV,OPS,DOC,DES,GAM,SPA,DSK}"
BENCH_SUBDIRS="${BENCH_SUBDIRS:-Eyeson_batch1,Eyeson_batch2,Eyeson_batch3,Eyeson_batch_gen}"
TASK_FILTER="${TASK_FILTER:-}"
LIMIT="${LIMIT:-0}"
MAX_STEPS="${MAX_STEPS:-100}"
CUA_NATIVE="${CUA_NATIVE:-0}"
RESULT_ROOT_BASE="${RESULT_ROOT_BASE:-${WCB_DIR}/output/openclaw_gui}"

ensure_litellm() {
  if ! curl -sS --max-time 5 --noproxy '*' \
      "http://${LITELLM_HOST_IP}:${LITELLM_PORT}/v1/models" \
      -H "Authorization: Bearer ${LITELLM_API_KEY}" \
      | grep -q "\"id\":\"${LITELLM_PRECHECK_MODEL}\""; then
    echo "[litellm] preflight FAILED — ${LITELLM_HOST_IP}:${LITELLM_PORT} not serving ${LITELLM_PRECHECK_MODEL}" >&2
    return 1
  fi
  echo "[litellm] preflight OK — ${LITELLM_PRECHECK_MODEL} on ${LITELLM_HOST_IP}:${LITELLM_PORT}"
}

ensure_judge_endpoint() {
  local probe
  probe=$(curl -sS --max-time 5 --noproxy '*' "${JUDGE_BASE_URL%/}/models" \
          ${JUDGE_API_KEY:+-H "Authorization: Bearer ${JUDGE_API_KEY}"} 2>&1)
  if ! echo "$probe" | grep -q "\"id\":\"${JUDGE_MODEL}\""; then
    echo "[judge-api] preflight FAILED — ${JUDGE_BASE_URL} not serving ${JUDGE_MODEL}" >&2
    return 1
  fi
  echo "[judge-api] preflight OK — ${JUDGE_MODEL} on ${JUDGE_BASE_URL}"
}

ensure_openclaw() {
  if [ ! -x "${AJ_OPENCLAW_BIN}" ]; then
    echo "[openclaw] preflight FAILED — bin not executable: ${AJ_OPENCLAW_BIN}" >&2
    return 1
  fi
  if [ ! -f "${HOME}/.openclaw-${AJ_OPENCLAW_PROFILE}/openclaw.json" ]; then
    echo "[openclaw] preflight FAILED — profile '${AJ_OPENCLAW_PROFILE}' not configured" >&2
    echo "[openclaw]   run: bash ${LAUNCHER_DIR}/setup_azure_judge_profile.sh" >&2
    return 1
  fi
  if [ ! -d "${AJ_TEMPLATE_PROFILE}" ] || [ ! -d "${AJ_TEMPLATE_WORKSPACE}" ]; then
    echo "[openclaw] preflight FAILED — templates missing:" >&2
    echo "  ${AJ_TEMPLATE_PROFILE}" >&2
    echo "  ${AJ_TEMPLATE_WORKSPACE}" >&2
    return 1
  fi
  echo "[openclaw] preflight OK — profile=${AJ_OPENCLAW_PROFILE}"
}

# launch_model <model-id> <runner-rel-path-under-eval/> <result-suffix> [extra args]
launch_model() {
  local MODEL="$1"
  local RUNNER="$2"
  local SUFFIX="$3"
  shift 3

  ensure_litellm        || return $?
  ensure_judge_endpoint || return $?
  ensure_openclaw       || return $?

  local AGENT_BASE_URL="http://${LITELLM_VM_IP}:${LITELLM_PORT}/v1"
  local RESULT_DIR="${RESULT_ROOT_BASE}/${MODEL}/${SUFFIX}"
  mkdir -p "${RESULT_DIR}"

  echo "==========================================================="
  echo "Repo (CUA-Claw-Harness): ${WCB_DIR}"
  echo "Bench data (read-only) : ${AJ_BENCH_ROOT}"
  echo "Backend (rollout)      : local LiteLLM ${LITELLM_VM_IP}:${LITELLM_PORT}  → Azure direct"
  echo "Backend (judge)        : ${JUDGE_BASE_URL}  (model ${JUDGE_MODEL})"
  echo "Model            : ${MODEL}"
  echo "Runner           : eval/${RUNNER}"
  echo "Mode             : ${MODE}    cua_native: ${CUA_NATIVE}"
  echo "Num envs         : ${NUM_ENVS}    max_steps: ${MAX_STEPS}"
  echo "Categories       : ${CATEGORIES}"
  echo "Bench subdirs    : ${BENCH_SUBDIRS}"
  echo "Task filter      : ${TASK_FILTER:-<all>}"
  echo "Result dir       : ${RESULT_DIR}"
  echo "Judge profile    : ${AJ_OPENCLAW_PROFILE}    workspace: ${AJ_JUDGE_WORKSPACE}"
  echo "Judge timeout    : ${AJ_TIMEOUT}s   thinking: ${AJ_THINKING}"
  echo "Start time       : $(date)"
  echo "==========================================================="

  cd "${WCB_DIR}"
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
  export NO_PROXY=127.0.0.1,172.17.0.1,localhost
  export no_proxy="${NO_PROXY}"

  # Make tasks_wcb point at AJ_BENCH_ROOT if not already
  if [ ! -e tasks_wcb ]; then
    ln -snf "${AJ_BENCH_ROOT}" tasks_wcb
  fi

  local SUBDIR_ARGS=()
  if [ -n "${BENCH_SUBDIRS}" ]; then
    SUBDIR_ARGS=(--bench_subdirs "${BENCH_SUBDIRS}")
  fi

  # wcb_root tells run_bench_gen / run_one_aj where to find the Eyeson_bench
  # data (which lives in the user's wildclawbench/, NOT in this repo).
  local AJ_WCB_ROOT
  AJ_WCB_ROOT="$(dirname "${AJ_BENCH_ROOT}")"

  "${PY_BIN}" "eval/${RUNNER}" \
    --provider_name docker \
    --headless \
    --num_envs "${NUM_ENVS}" \
    --mode "${MODE}" \
    "${SUBDIR_ARGS[@]}" \
    --categories "${CATEGORIES}" \
    ${TASK_FILTER:+--task_filter "${TASK_FILTER}"} \
    ${LIMIT:+$( [ "${LIMIT}" -gt 0 ] && echo "--limit ${LIMIT}" )} \
    --model "${MODEL}" \
    --litellm_base_url "${AGENT_BASE_URL}" \
    --litellm_api_key "${LITELLM_API_KEY}" \
    --max_steps "${MAX_STEPS}" \
    --cua_native "${CUA_NATIVE}" \
    --wcb_root "${AJ_WCB_ROOT}" \
    --result_dir "${RESULT_DIR}" \
    "$@" 2>&1 | tee "${RESULT_DIR}/run_$(date +%Y%m%d_%H%M%S).log"
}
