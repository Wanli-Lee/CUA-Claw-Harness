"""openclaw_gui — thin wrapper around the AJ-GUI launcher.

Unlike openclaw/claudecode/codex/hermesagent which all implement the
BaseAgent contract directly inside CUA-Claw-Harness, openclaw_gui
delegates to the imported wildclawbench AJ pipeline at
``eval/agent_judge/run_bench_gen_aj.py`` (which spins up a full
DesktopEnv KVM, runs OpenClaw in GUI mode, and grades via
Agent-as-Judge instead of the in-VM Python grader).

Invoked by ``script/run_wcb.sh openclaw_gui ...`` which forwards to
``script/launchers_aj_gui/run_gpt_5_5.sh`` (or another model entry)
with the right env wiring.
"""
