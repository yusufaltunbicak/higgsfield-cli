"""Automated browser bridge for DataDome-protected POST requests.

When direct API calls get blocked by DataDome (403), this module
automatically ensures Chrome has a higgsfield.ai tab and executes
the request through Chrome's authenticated page context.

The user does NOT need to manually open Chrome or navigate to any URL.
"""

from __future__ import annotations

import json
import subprocess
import time

from .constants import API_BASE
from .exceptions import HiggsError


def _ensure_chrome_tab() -> bool:
    """Ensure Chrome has a higgsfield.ai tab. Opens one silently if needed.

    Does NOT activate/focus Chrome - works entirely in the background.
    Returns True if a tab is available, False if Chrome can't be used.
    """
    import platform
    if platform.system() != "Darwin":
        return False

    # First check if Chrome is running at all
    try:
        pgrep = subprocess.run(
            ["pgrep", "-x", "Google Chrome"],
            capture_output=True, timeout=3,
        )
        chrome_running = pgrep.returncode == 0
    except Exception:
        chrome_running = False

    if not chrome_running:
        # Launch Chrome silently in background (no activate)
        try:
            subprocess.Popen(
                ["open", "-g", "-a", "Google Chrome", "https://higgsfield.ai/image/nano_banana_2"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    # Chrome is running - check for higgsfield tab and create one if missing
    # Using "without activating" to keep Chrome in the background
    script = '''
tell application "Google Chrome"
    -- Look for existing higgsfield tab
    set found to false
    if (count of windows) > 0 then
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "higgsfield.ai" then
                    set found to true
                    exit repeat
                end if
            end repeat
            if found then exit repeat
        end repeat
    end if

    if not found then
        if (count of windows) = 0 then
            make new window
        end if
        tell window 1
            make new tab with properties {URL:"https://higgsfield.ai/image/nano_banana_2"}
        end tell
    end if
    return "OK"
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _wait_for_tab_ready(timeout: float = 20) -> bool:
    """Wait until the higgsfield.ai tab has a loaded editor."""
    from .chrome_bridge import _run_js

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            found = _run_js(
                "document.querySelector('[contenteditable=true]') ? 'yes' : 'no'"
            )
            if found == "yes":
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def post_via_browser(url: str, body: dict, token: str) -> dict:
    """Execute a POST request through Chrome's page context.

    Automatically opens Chrome with a higgsfield.ai tab if needed,
    then drives the UI to submit the generation request and captures
    the API response.
    """
    from .chrome_bridge import is_available, _run_js, _run_async_js

    # Step 1: Ensure Chrome has a higgsfield tab (always check, even if Chrome is running)
    if not _ensure_chrome_tab():
        raise HiggsError(
            "Chrome is required for image generation (DataDome bypass).\n"
            "Please install Google Chrome."
        )
    # Wait for tab to be ready
    if not _wait_for_tab_ready(timeout=25):
        raise HiggsError(
            "Chrome tab failed to load. Please check your internet connection."
        )

    # Step 2: Execute POST via XHR in page context
    # Use XMLHttpRequest (sync) which DataDome's SDK intercepts properly
    body_json = json.dumps(body).replace("\\", "\\\\").replace("'", "\\'")
    js = f"""
        return (async () => {{
            const resp = await fetch("{url}", {{
                method: "POST",
                headers: {{
                    "Authorization": "Bearer {token}",
                    "Content-Type": "application/json",
                }},
                body: '{body_json}',
                credentials: "include",
            }});
            const text = await resp.text();
            return resp.status + "|" + text;
        }})();
    """

    try:
        raw = _run_async_js(js, timeout=20)
    except Exception:
        raw = ""

    if raw and "|" in raw:
        status_str, response_text = raw.split("|", 1)
        try:
            status = int(status_str)
        except ValueError:
            status = 0

        if status == 200 or status == 201:
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                return {"_raw": response_text}

        if status == 403 and ("<html" in response_text[:50].lower()):
            # DataDome still blocking via fetch - fall back to UI-driven approach
            pass
        elif status >= 400:
            _raise_for_status(status, response_text)
    else:
        # fetch failed (CORS, DataDome intercept, etc.)
        pass

    # Step 3: Fallback - drive the UI directly (like chrome_bridge.generate_via_chrome)
    # This is more reliable as DataDome's JS SDK handles the request
    return _generate_via_ui(url, body, token)


def _generate_via_ui(url: str, body: dict, token: str) -> dict:
    """Generate by driving the Higgsfield UI in Chrome.

    Extracts params from the request body and fills the UI form.
    Returns the API response captured from network activity.
    """
    from .chrome_bridge import _run_js, generate_via_chrome
    from .constants import MODELS

    params = body.get("params", {})
    prompt = params.get("prompt", "")
    aspect_ratio = params.get("aspect_ratio", "16:9")
    batch_size = params.get("batch_size", 4)
    resolution = params.get("resolution", "4k")
    quality = params.get("quality", "high")
    use_unlim = body.get("use_unlim", False)

    # Determine model slug from URL
    model_slug = url.split("/jobs/")[-1].split("/")[-1] if "/jobs/" in url else "nano-banana-2"
    # Handle v2 endpoints
    model_slug = model_slug.replace("v2/", "")

    result = generate_via_chrome(
        prompt=prompt,
        model_slug=model_slug,
        resolution=resolution,
        quality=quality,
        aspect_ratio=aspect_ratio,
        batch_size=batch_size,
        use_unlim=use_unlim,
    )

    if result and result.get("status") == "submitted":
        # Poll history to find the new job ID
        poll_result = _poll_for_new_job(prompt, token)
        job_id = poll_result.get("jobs", [{}])[0].get("job_set_id", "")

        if not job_id:
            raise HiggsError(
                "Job submitted but not found in history.\n"
                "Run 'higgsfield watch --all' to check."
            )

        # Return in GenerateResponse.from_api expected format
        return {
            "id": "",
            "job_sets": [{
                "id": job_id,
                "jobs": [{"id": job_id, "status": "waiting"}],
            }],
        }

    raise HiggsError("Failed to submit generation via Chrome UI")


def _poll_for_new_job(prompt: str, token: str) -> dict:
    """Poll API history via Chrome to find the newly submitted job.

    Uses Chrome's page context (via AppleScript) for polling to avoid
    DataDome blocking that can affect direct httpx calls.
    Returns a dict with job_set_id that GenerateResponse can use.
    """
    from .chrome_bridge import _run_async_js

    prompt_prefix = prompt[:20].replace("'", "\\'").replace('"', '\\"')

    for attempt in range(8):
        time.sleep(3)
        try:
            # Only return the job_set_id to avoid document.title size limits
            js = f"""
                return (async () => {{
                    const resp = await fetch("https://fnf.higgsfield.ai/jobs/accessible?size=5&job_set_type=nano_banana_2&job_set_type=nano_banana_flash&job_set_type=seedream_v4_5&job_set_type=seedream_v5_lite&job_set_type=flux_2&job_set_type=kling_omni_image", {{
                        headers: {{
                            "Authorization": "Bearer {token}",
                        }},
                        credentials: "include",
                    }});
                    if (resp.status !== 200) return "ERR:" + resp.status;
                    const data = await resp.json();
                    const jobs = data.jobs || [];
                    const match = jobs.find(j => (j.params?.prompt || "").includes("{prompt_prefix}"));
                    if (match) return "OK:" + match.job_set_id;
                    return "NOTFOUND";
                }})();
            """
            raw = _run_async_js(js, timeout=15)

            if raw and raw.startswith("OK:"):
                job_id = raw[3:].strip()
                # Return minimal structure that GenerateResponse.from_api can parse
                return {"jobs": [{"job_set_id": job_id}]}
            if raw and raw.startswith("ERR:"):
                continue
            # NOTFOUND - keep polling
        except Exception:
            continue

    raise HiggsError(
        "Job submitted via Chrome but not found in history.\n"
        "Run 'higgsfield watch --all' to check."
    )


def _raise_for_status(status: int, text: str):
    """Raise appropriate exception for HTTP status."""
    from .exceptions import (
        TokenExpiredError,
        RateLimitError,
        InsufficientCreditsError,
    )

    if status == 401:
        raise TokenExpiredError("Token expired. Run: higgsfield login")
    if status == 402:
        raise InsufficientCreditsError("Not enough credits.")
    if status == 429:
        raise RateLimitError("Rate limit hit. Wait and try again.")

    detail = ""
    try:
        detail = json.loads(text).get("detail", "")
    except Exception:
        pass
    raise HiggsError(f"API error (HTTP {status}). {detail}")


def close_browser():
    """No-op for compatibility - Chrome stays running."""
    pass
