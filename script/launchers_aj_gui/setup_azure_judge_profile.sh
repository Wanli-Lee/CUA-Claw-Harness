#!/usr/bin/env bash
# One-time setup: provision an isolated OpenClaw judge profile pointing at
# the local litellm proxy (port 4200) for the AJ-GUI-Azure batch.
#
# Usage:
#   bash setup_azure_judge_profile.sh
#
# Idempotent — safe to re-run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_BIN="${OPENCLAW_BIN:-${HOME}/judge_agent_test/node_modules/.bin/openclaw}"
PROFILE_NAME="${PROFILE_NAME:-azure_judge}"
WORKSPACE="${WORKSPACE:-${HOME}/judge_agent_test/azure_judge_workspace}"
LITELLM_PORT="${LITELLM_PORT:-4200}"
LITELLM_KEY="${LITELLM_KEY:-sk-litellm-azure-direct}"

if [ ! -x "$OPENCLAW_BIN" ]; then
  echo "ERROR: openclaw not found at $OPENCLAW_BIN" >&2
  exit 1
fi

# Verify litellm is up first
if ! curl -sS --max-time 5 --noproxy '*' "http://127.0.0.1:${LITELLM_PORT}/v1/models" \
     -H "Authorization: Bearer ${LITELLM_KEY}" | grep -q '"id":"gpt-5.5"'; then
  echo "ERROR: litellm proxy not serving gpt-5.5 on :${LITELLM_PORT}" >&2
  echo "  start it with: bash $(dirname "$HERE")/../litellm_azure_direct/start.sh" >&2
  exit 2
fi

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
export NO_PROXY=127.0.0.1,localhost

echo "[setup] provisioning profile: $PROFILE_NAME → http://127.0.0.1:${LITELLM_PORT}"
"$OPENCLAW_BIN" --profile "$PROFILE_NAME" onboard \
  --non-interactive --accept-risk \
  --workspace "$WORKSPACE" \
  --auth-choice custom-api-key \
  --custom-api-key "$LITELLM_KEY" \
  --custom-base-url "http://127.0.0.1:${LITELLM_PORT}/v1" \
  --custom-model-id gpt-5.5 \
  --custom-image-input \
  --custom-compatibility openai \
  --skip-channels --skip-daemon --skip-skills --skip-search --skip-ui --skip-health

echo "[setup] patching profile config (api: openai-responses, ctx 200K, image model)..."
PROFILE_CFG="${HOME}/.openclaw-${PROFILE_NAME}/openclaw.json"
python3 - <<PY
import json, os
p = "${PROFILE_CFG}"
c = json.load(open(p))
prov_key = next(k for k in c['models']['providers'] if 'custom' in k)
prov = c['models']['providers'][prov_key]
prov['api'] = 'openai-responses'
prov['models'][0]['contextWindow'] = 200000
prov['models'][0]['maxTokens'] = 16000
prov['models'][0]['reasoning'] = True
c.setdefault('agents', {}).setdefault('defaults', {})['imageModel'] = f"{prov_key}/gpt-5.5"
json.dump(c, open(p, 'w'), indent=2)
print(f"  patched {p}")
PY

# Replace persona files with eval-engineer persona (from existing template)
EXISTING_TEMPLATE="${HOME}/judge_agent_test/template_workspace"
if [ -d "$EXISTING_TEMPLATE" ]; then
  echo "[setup] copying persona files from $EXISTING_TEMPLATE → $WORKSPACE"
  for f in SOUL.md AGENTS.md IDENTITY.md TOOLS.md USER.md HEARTBEAT.md; do
    [ -f "$EXISTING_TEMPLATE/$f" ] && cp "$EXISTING_TEMPLATE/$f" "$WORKSPACE/$f"
  done
  rm -f "$WORKSPACE/BOOTSTRAP.md"
fi

# Build template dirs (used by judge_runner per-case isolation)
TPL_PROFILE="${HOME}/judge_agent_test/template_profile_azure"
TPL_WORKSPACE="${HOME}/judge_agent_test/template_workspace_azure"
echo "[setup] building template_profile_azure + template_workspace_azure"
rm -rf "$TPL_PROFILE" "$TPL_WORKSPACE"
mkdir -p "$TPL_PROFILE/agents/main/sessions" "$TPL_PROFILE/logs" "$TPL_PROFILE/tasks" "$TPL_PROFILE/plugin-skills"
cp "$PROFILE_CFG" "$TPL_PROFILE/openclaw.json"
mkdir -p "$TPL_WORKSPACE"
for f in SOUL.md AGENTS.md IDENTITY.md TOOLS.md USER.md HEARTBEAT.md; do
  [ -f "$WORKSPACE/$f" ] && cp "$WORKSPACE/$f" "$TPL_WORKSPACE/$f"
done

echo "[setup] DONE"
echo "  profile  : $PROFILE_CFG"
echo "  workspace: $WORKSPACE"
echo "  template : $TPL_PROFILE  +  $TPL_WORKSPACE"
echo
echo "[setup] smoke test..."
"$OPENCLAW_BIN" --profile "$PROFILE_NAME" agent --local --session-id setup_smoke \
  --message "Reply with 'AZURE-JUDGE-OK' and nothing else." 2>&1 | tail -3
