# CUA-Claw-Harness — backend docker images

| Tag | Built by | What's inside |
|---|---|---|
| `wildclawbench-codex-ubuntu:v0.1` | `Dockerfile.codex` | base + codex CLI 0.130.0 (`/usr/local/bin/codex`) |
| `wildclawbench-claudecode-ubuntu:v0.1` | `Dockerfile.claudecode` | base + claude-code CLI 2.1.76 (`/usr/local/bin/claude`) + `/claude_code/start.sh` shim |
| `wildclawbench-hermes-agent:v0.1` | `Dockerfile.hermes` | base + python 3.11 + NousResearch/hermes-agent@main installed editable at `/opt/hermes` |

All three are based on **`wildclawbench-ubuntu:v1.2`** so the openclaw-side
warmup scripts (xrandr / pyautogui / tesseract / ...) continue to work.

## Build commands (need host with clash proxy at 127.0.0.1:7890)

```bash
# All builds require --network host so the container reaches the host's proxy.
docker build --network host -f docker/Dockerfile.codex       -t wildclawbench-codex-ubuntu:v0.1 .
docker build --network host -f docker/Dockerfile.claudecode  -t wildclawbench-claudecode-ubuntu:v0.1 .

# Hermes additionally needs the upstream source cloned into the build context:
mkdir -p docker/_build_context
git clone --depth 1 https://github.com/NousResearch/hermes-agent.git docker/_build_context/hermes-agent
rm -rf docker/_build_context/hermes-agent/.git
docker build --network host -f docker/Dockerfile.hermes      -t wildclawbench-hermes-agent:v0.1 .
```

## Override build proxy

If you're on a host with a different clash port:

```bash
docker build --network host --build-arg BUILD_PROXY=http://127.0.0.1:7891 ...
```

## Verify

```bash
docker run --rm wildclawbench-codex-ubuntu:v0.1       codex --version
docker run --rm wildclawbench-claudecode-ubuntu:v0.1  claude --version
docker run --rm wildclawbench-hermes-agent:v0.1 \
    /opt/hermes/.venv/bin/python3 -c "import sys; sys.path.insert(0,'/opt/hermes'); from run_agent import AIAgent; print('OK')"
```
