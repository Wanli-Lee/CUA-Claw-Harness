from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

import yaml

load_dotenv()
# Resolve task-relative paths from repository root, not src/.
ROOT_DIR = Path(__file__).resolve().parents[2]


def _strip_leading_html_comments(text: str) -> str:
    """Strip any leading HTML comments + blank lines so the YAML frontmatter
    regex anchored at start-of-file still matches. Eyeson_bench batch3 tasks
    prepend a `<!-- resources: ... -->` block above the `---` fence.
    """
    out = text
    while True:
        out = out.lstrip("\ufeff").lstrip()
        if not out.startswith("<!--"):
            return out
        end = out.find("-->")
        if end < 0:
            return text  # malformed, leave alone — original error will surface
        out = out[end + 3:]


def parse_task_md(task_file: Path) -> dict:
    """Extract task_id, prompt, workspace_path, and automated_checks from task.md.

    Tolerates a leading HTML comment block (used by Eyeson_bench batch3 .md
    files to carry a machine-readable resources manifest above the YAML
    frontmatter).
    """
    raw = task_file.read_text(encoding="utf-8")
    content = _strip_leading_html_comments(raw)

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"YAML frontmatter not found: {task_file}")

    metadata = yaml.safe_load(fm_match.group(1))
    body     = fm_match.group(2)

    sections: dict[str, str] = {}
    current_section: Optional[str] = None
    lines: list[str] = []
    for line in body.split("\n"):
        header = re.match(r"^##\s+(.+)$", line)
        if header:
            if current_section is not None:
                sections[current_section] = "\n".join(lines).strip()
            current_section = header.group(1)
            lines = []
        else:
            lines.append(line)
    if current_section is not None:
        sections[current_section] = "\n".join(lines).strip()

    def strip_codeblock(raw: str) -> str:
        s = re.sub(r"^```[^\n]*\n?", "", raw.strip())
        s = re.sub(r"\n?```$", "", s).strip()
        # Also strip a single pair of wrapping inline backticks (used in
        # Eyeson_bench ## Workspace Path sections for prettier rendering).
        if s.startswith("`") and s.endswith("`") and len(s) >= 2:
            s = s[1:-1].strip()
        return s

    prompt = sections.get("Prompt", "").strip()

    raw_workspace  = sections.get("Workspace Path", "").strip()
    workspace_path = strip_codeblock(raw_workspace)
    # ## Workspace Path may include trailing commentary lines (Eyeson_bench
    # batch3 DOC_task_12, WEB_task_13). Keep only the first non-empty line.
    if workspace_path:
        first = next((ln.strip() for ln in workspace_path.splitlines() if ln.strip()), "")
        if first.startswith("`") and first.endswith("`") and len(first) >= 2:
            first = first[1:-1].strip()
        workspace_path = first
    if not workspace_path:
        raise ValueError(f"Missing ## Workspace Path in task.md: {task_file}")

    skills_path = "skills"

    automated_checks = strip_codeblock(sections.get("Automated Checks", ""))
    env    = strip_codeblock(sections.get("Env",    ""))
    skills = strip_codeblock(sections.get("Skills",    ""))
    warmup = strip_codeblock(sections.get("Warmup", ""))

    task_id         = metadata.get("id",             task_file.stem)
    timeout_seconds = int(metadata.get("timeout_seconds", 120))

    wp = Path(workspace_path)
    if not wp.is_absolute():
        # Try resolving relative to several candidate roots, in order:
        #   1. The task .md's grandparent (the "batch dir" in Eyeson_bench
        #      layout: tasks_wcb/batch1/<CAT>/<task>.md → batch1/)
        #   2. The task .md's parent (sibling-of-task)
        #   3. ROOT_DIR (upstream convention: tasks/<CAT>/<task>.md →
        #      workspace/<CAT>/<task>/ both under repo root)
        # First match that exists on disk wins; otherwise fall back to ROOT.
        candidates = [
            task_file.parent.parent / workspace_path,  # batch-dir
            task_file.parent / workspace_path,         # task-sibling
            ROOT_DIR / workspace_path,                 # repo root
        ]
        # Eyeson_bench batch3 sometimes hardcodes a legacy
        # "wen_tasks/<batch>/workspace/..." path. Strip that prefix and try
        # again relative to the actual batch dir.
        m = re.match(r"^wen_tasks/[^/]+/(workspace/.*)$", workspace_path)
        if m:
            stripped = m.group(1)
            candidates.append(task_file.parent.parent / stripped)
        wp_resolved = None
        for c in candidates:
            try:
                if c.resolve().is_dir():
                    wp_resolved = c.resolve()
                    break
            except OSError:
                continue
        wp = wp_resolved or (ROOT_DIR / workspace_path).resolve()
    workspace_path = str(wp)

    sp = Path(skills_path)
    if not sp.is_absolute():
        sp = (ROOT_DIR / sp).resolve()
    skills_path = str(sp)

    return {
        "task_id":          task_id,
        "prompt":           prompt,
        "workspace_path":   workspace_path,
        "skills_path":      skills_path,
        "automated_checks": automated_checks,
        "env":              env,
        "skills":           skills,
        "warmup":           warmup,
        "timeout_seconds":  timeout_seconds,
        "file_path":        str(task_file.resolve()),
        "category":         task_file.parent.name,
    }
