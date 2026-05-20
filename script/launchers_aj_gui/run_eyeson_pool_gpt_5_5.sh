#!/usr/bin/env bash
# Pool wrapper for AJ-GUI gpt-5.5 (CUA-Claw-Harness).
# Adapted from wildclawbench/eval/launchers_aj_gui_azure/run_eyeson_pool_gpt_5_5.sh.
#
# NUM_ENVS parallel KVM VMs share one global queue across all 4 Eyeson batches.
# ds.already_done() auto-skips completed score.json.
#
# Output: <repo>/output/openclaw_gui/<MODEL>/<RESULT_TAG>/<bench>/gui/<MODEL>/<CAT>/<task>/
set -uo pipefail

LAUNCHER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(cd "${LAUNCHER_DIR}/.." && pwd)"
WCB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export NUM_ENVS="${NUM_ENVS:-10}"
export OSWORLD_RAM_SIZE="${OSWORLD_RAM_SIZE:-8G}"
export OSWORLD_CPU_CORES="${OSWORLD_CPU_CORES:-4}"
export CATEGORIES="${CATEGORIES:-WEB,DAV,OPS,DOC,DES,GAM,SPA,DSK}"
export TASK_FILTER="${TASK_FILTER:-task_}"
export MODE="${MODE:-gui}"
export CUA_NATIVE="${CUA_NATIVE:-0}"
export MAX_STEPS="${MAX_STEPS:-100}"

export LITELLM_PORT="${LITELLM_PORT:-4200}"
export LITELLM_HOST_IP="${LITELLM_HOST_IP:-127.0.0.1}"
export LITELLM_VM_IP="${LITELLM_VM_IP:-172.17.0.1}"
export LITELLM_API_KEY="${LITELLM_API_KEY:-sk-litellm-azure-direct}"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

# Judge backend — cop-api at 4141 (no key).
export JUDGE_HOST_IP="${JUDGE_HOST_IP:-127.0.0.1}"
export JUDGE_VM_IP="${JUDGE_VM_IP:-172.17.0.1}"
export JUDGE_PORT="${JUDGE_PORT:-4141}"
export JUDGE_BASE_URL="${JUDGE_BASE_URL:-http://${JUDGE_HOST_IP}:${JUDGE_PORT}/v1}"
export JUDGE_API_KEY="${JUDGE_API_KEY:-}"
export JUDGE_MODEL="${JUDGE_MODEL:-gpt-5.5}"

export BENCH_SUBDIRS="${BENCH_SUBDIRS:-Eyeson_batch1,Eyeson_batch2,Eyeson_batch3,Eyeson_batch_gen}"

export AJ_TIMEOUT="${AJ_TIMEOUT:-1800}"
export AJ_THINKING="${AJ_THINKING:-medium}"
export AJ_OPENCLAW_PROFILE="${AJ_OPENCLAW_PROFILE:-azure_judge}"

MODEL=gpt-5.5
DATE_TAG="$(date +%Y%m%d)"
RESULT_TAG="${RESULT_TAG:-AJ_GUI_${DATE_TAG}}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${WCB_DIR}/output/_run_logs/${MODEL}_${RESULT_TAG}_aj_gui_pool_${TS}"
mkdir -p "${LOG_DIR}"
export RESULT_ROOT_BASE="${RESULT_ROOT_BASE:-${WCB_DIR}/output/openclaw_gui}"

echo "==========================================================="
echo "[pool wrapper] ts            : ${TS}"
echo "[pool wrapper] model         : ${MODEL}  (azure/gpt-5.5 via local litellm)"
echo "[pool wrapper] result_tag    : ${RESULT_TAG}"
echo "[pool wrapper] num_envs      : ${NUM_ENVS}    ram: ${OSWORLD_RAM_SIZE}"
echo "[pool wrapper] mode          : ${MODE}    cua_native: ${CUA_NATIVE}"
echo "[pool wrapper] max_steps     : ${MAX_STEPS}"
echo "[pool wrapper] bench_subdirs : ${BENCH_SUBDIRS}"
echo "[pool wrapper] categories    : ${CATEGORIES}"
echo "[pool wrapper] result_root_base: ${RESULT_ROOT_BASE}"
echo "[pool wrapper] log_dir       : ${LOG_DIR}"
echo "[pool wrapper] backend(rollout): local litellm ${LITELLM_VM_IP}:${LITELLM_PORT} → Azure direct"
echo "[pool wrapper] backend(judge) : ${JUDGE_BASE_URL}  model=${JUDGE_MODEL}"
echo "==========================================================="

bash "${LAUNCHER_DIR}/run_gpt_5_5.sh" 2>&1 \
  | tee "${LOG_DIR}/pool.log"
RC=${PIPESTATUS[0]}

echo
echo "[pool wrapper] finished at $(date)  exit=${RC}"
echo "[pool wrapper] log: ${LOG_DIR}/pool.log"
