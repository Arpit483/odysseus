"""Regression test for checklist double-click race condition.

Extracts the click/dblclick listeners from notes.js and drives them against
a stubbed DOM to verify that a double-click gesture correctly enters edit mode
without triggering the single-click checkbox toggle.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HAS_NODE = shutil.which("node") is not None


@pytest.fixture(scope="module")
def node_available():
    if not _HAS_NODE:
        pytest.skip("node binary not on PATH")


def _run_node(script: str) -> dict:
    res = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=_REPO,
        capture_output=True,
        timeout=15,
        text=True,
    )
    if res.returncode != 0:
        raise AssertionError(f"node failed:\n{res.stderr}")
    out_lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    if not out_lines:
        raise AssertionError("node produced no stdout")
    return json.loads(out_lines[-1])


def test_checklist_dblclick_bypasses_toggle_via_debounce(node_available):
    src = (_REPO / "static" / "js" / "notes.js").read_text(encoding="utf-8")
    
    # Extract the block attaching click/dblclick to .note-check-text
    match = re.search(r"(body\.querySelectorAll\('\.note-check-text'\)\.forEach[\s\S]+?\}\);\s*\}\);)", src)
    if not match:
        raise AssertionError("Could not find .note-check-text listeners in notes.js")
    
    block = match.group(1)

    script = f"""
    let toggleCount = 0;
    let editStarted = false;
    
    const parent = {{
        dataset: {{ noteId: "1", idx: "0" }},
        // A click on the parent (the checkbox row) represents the toggle path
        click: () => {{ toggleCount++; }},
    }};
    
    const span = {{
        isContentEditable: false,
        listeners: {{}},
        addEventListener: (event, handler) => {{
            span.listeners[event] = handler;
        }},
        closest: (sel) => sel === '.note-checkbox' ? parent : null,
    }};
    
    globalThis._selectMode = false;
    globalThis._startChecklistItemEdit = () => {{ editStarted = true; }};
    
    const body = {{
        querySelectorAll: () => [span]
    }};
    
    // Evaluate the extracted listener attachment logic
    {block}
    
    // The simulated event object
    const e = {{ stopPropagation: () => {{}} }};
    
    // Step 1: Render a checklist item with done = false (done via our mock)
    // Step 2: Double-click the checklist text
    // The browser fires: click, click, dblclick in rapid succession
    
    span.listeners['click'](e);
    span.listeners['click'](e);
    span.listeners['dblclick'](e);
    
    // Wait slightly longer than the 250ms debounce timeout to ensure 
    // the single-click timeout does not fire incorrectly.
    setTimeout(() => {{
        console.log(JSON.stringify({{ editStarted, toggleCount }}));
    }}, 300);
    """
    
    out = _run_node(script)
    
    # Step 3: Assert
    # - Edit mode is active
    # - The completion-toggle update function was not called (parent.click() not invoked)
    assert out["editStarted"] is True
    assert out["toggleCount"] == 0

