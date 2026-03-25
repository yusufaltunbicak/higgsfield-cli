"""Chrome bridge - execute Higgsfield actions via Chrome's UI.

Uses AppleScript to control Chrome for operations that require
DataDome-authenticated requests (POST /jobs/*).

GET requests work directly via httpx with JWT token.
POST /jobs/* requests must go through Chrome's page context.
"""

from __future__ import annotations

import json
import subprocess
import time


def is_available() -> bool:
    """Check if Chrome bridge is available (only if Chrome is already running)."""
    import platform
    if platform.system() != "Darwin":
        return False
    try:
        # Don't launch Chrome - check if it's already running
        pgrep = subprocess.run(
            ["pgrep", "-x", "Google Chrome"],
            capture_output=True, timeout=3,
        )
        if pgrep.returncode != 0:
            return False
        result = subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to return name of window 1'],
            capture_output=True, text=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _run_js(js_code: str, timeout: float = 5) -> str:
    """Execute JavaScript in the first higgsfield.ai tab found in Chrome."""
    # Escape for AppleScript string embedding
    escaped_js = js_code.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
tell application "Google Chrome"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "higgsfield.ai" then
                tell t
                    return execute javascript "{escaped_js}"
                end tell
            end if
        end repeat
    end repeat
    return "NO_HIGGSFIELD_TAB"
end tell
'''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip()


def _run_async_js(js_code: str, timeout: float = 15) -> str:
    """Execute async JavaScript by storing result in document.title."""
    # Wrap in async IIFE that stores result in title (save original first)
    wrapper = f"""
        (async () => {{
            try {{
                if (!window.__hf_orig_title) window.__hf_orig_title = document.title;
                const __result = await (async () => {{ {js_code} }})();
                document.title = "RESULT:" + (__result || "");
            }} catch(e) {{
                document.title = "ERROR:" + e.message;
            }}
        }})()
    """
    escaped = wrapper.replace("\\", "\\\\").replace('"', '\\"')

    # First, execute the async code
    script_exec = f'''
tell application "Google Chrome"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "higgsfield.ai" then
                tell t
                    execute javascript "{escaped}"
                end tell
                exit repeat
            end if
        end repeat
    end repeat
end tell
'''
    subprocess.run(["osascript", "-e", script_exec], capture_output=True, timeout=5)

    # Poll for result
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        title = _get_tab_title()
        if title.startswith("RESULT:"):
            _restore_title()
            return title[7:]
        if title.startswith("ERROR:"):
            _restore_title()
            raise RuntimeError(title[6:])
    _restore_title()
    return ""


def _get_tab_title() -> str:
    script = '''
tell application "Google Chrome"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "higgsfield.ai" then
                return name of t
            end if
        end repeat
    end repeat
    return ""
end tell
'''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
    return result.stdout.strip()


def _restore_title() -> str:
    """Restore the original page title."""
    _run_js("document.title = window.__hf_orig_title || document.querySelector('title')?.textContent || 'Higgsfield'; delete window.__hf_orig_title")
    return ""


def generate_via_chrome(
    prompt: str,
    model_slug: str = "nano-banana-2",
    resolution: str = "4k",
    quality: str = "high",
    aspect_ratio: str = "16:9",
    batch_size: int = 4,
    use_unlim: bool = False,
) -> dict | None:
    """Generate images by driving Chrome's Higgsfield UI.

    Returns the API response dict, or None on failure.
    """
    # Ensure we're on the right page
    current_url = _run_js("document.location.href")
    if "higgsfield.ai" not in current_url:
        return None

    # Navigate to the correct model page if needed
    # Model slug to URL path mapping
    model_paths = {
        "nano-banana-2": "nano_banana_2",
        "nano_banana_flash": "nano_banana_flash",
        "seedream-v4-5": "seedream_v4_5",
        "seedream-v5-lite": "seedream_v5_lite",
        "flux-2": "flux_2",
        "kling-omni-image": "kling_omni_image",
    }
    path = model_paths.get(model_slug, "nano_banana_2")
    target_url = f"https://higgsfield.ai/image/{path}"

    if path not in current_url:
        _run_js(f"window.location.href = '{target_url}'")
        time.sleep(3)

    # Clear and set prompt using execCommand (triggers React state properly)
    _run_js("""
        var editor = document.querySelector('[contenteditable=true]');
        if (editor) {
            editor.focus();
            editor.innerHTML = '';
            editor.dispatchEvent(new Event('input', {bubbles: true}));
        }
    """)
    time.sleep(0.3)

    _run_js("""
        var editor = document.querySelector('[contenteditable=true]');
        if (editor) {
            editor.focus();
            document.execCommand('selectAll', false);
            document.execCommand('delete', false);
        }
    """)
    time.sleep(0.3)

    # Insert prompt text
    safe_prompt = prompt.replace("'", "\\'").replace('"', '\\"').replace("\n", " ")
    _run_js(f"""
        var editor = document.querySelector('[contenteditable=true]');
        if (editor) {{
            editor.focus();
            document.execCommand('insertText', false, '{safe_prompt}');
        }}
    """)
    time.sleep(0.5)

    # Set aspect ratio via UI
    _set_aspect_ratio(aspect_ratio)
    time.sleep(0.5)

    # Click Generate
    _run_js("""
        var genBtn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Generate'));
        if (genBtn) genBtn.click();
    """)
    time.sleep(2)

    return {"status": "submitted", "prompt": prompt}


def _set_aspect_ratio(ratio: str) -> None:
    """Click the aspect ratio selector in Higgsfield UI."""
    # First click the current ratio button to open dropdown
    _run_js("""
        var ratioBtn = [...document.querySelectorAll('button')].find(b => {
            var t = b.textContent.trim();
            return ['Auto','1:1','16:9','9:16','4:3','3:4','21:9','3:2','2:3'].includes(t);
        });
        if (ratioBtn) ratioBtn.click();
    """)
    time.sleep(0.5)

    # Then click the desired ratio from dropdown
    safe_ratio = ratio.replace("'", "\\'")
    _run_js(f"""
        var options = [...document.querySelectorAll('div')].filter(e =>
            e.textContent.trim() === '{safe_ratio}' && e.className.includes('flex flex-1')
        );
        if (options.length > 0) options[0].click();
    """)
    time.sleep(0.3)


def get_token_from_chrome() -> str | None:
    """Get fresh JWT from Chrome's __session cookie."""
    try:
        token = _run_js(
            "var m = document.cookie.match(/__session=([^;]+)/); m ? m[1] : ''"
        )
        if token and token.startswith("eyJ") and len(token) > 100:
            return token
    except Exception:
        pass
    return None
