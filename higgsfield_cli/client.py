"""HTTP client for Higgsfield API."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import httpx

from .constants import (
    API_BASE,
    ASPECT_RATIOS,
    CACHE_DIR,
    MODELS,
    USER_AGENT,
)
from .exceptions import (
    HiggsError,
    InsufficientCreditsError,
    JobFailedError,
    RateLimitError,
    ResourceNotFoundError,
    TokenExpiredError,
)
from .models import GenerateResponse, Job, UserInfo, Wallet


class HiggsClient:
    """HTTP client for Higgsfield fnf API."""

    MAX_ID_MAP_SIZE = 200

    def __init__(self, token: str):
        self._token = token
        from .auth import get_datadome_cookie
        cookies = {}
        dd = get_datadome_cookie()
        if dd:
            cookies["datadome"] = dd
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
            },
            cookies=cookies,
            timeout=30,
        )
        self._id_map: dict[str, str] = self._load_id_map()
        self._next_num: int = max(
            (int(k) for k in self._id_map if k.isdigit()), default=0
        ) + 1

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        model: str = "nano-banana-pro",
        resolution: str = "4k",
        quality: str = "high",
        aspect_ratio: str = "16:9",
        batch_size: int = 4,
        seed: int | None = None,
        use_unlim: bool = False,
        use_seedream_bonus: bool = False,
        input_images: list[dict] | None = None,
    ) -> GenerateResponse:
        """Create an image generation job."""
        if model not in MODELS:
            raise ValueError(
                f"Unknown model: {model}. Available: {', '.join(MODELS)}"
            )

        url_slug, job_set_type, version = MODELS[model]
        width, height = ASPECT_RATIOS.get(aspect_ratio, (1024, 1024))

        # Build params based on model type
        params: dict = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "batch_size": batch_size,
            "aspect_ratio": aspect_ratio,
            "use_unlim": use_unlim,
        }

        if "seedream" in model:
            # Seedream models use quality + seed instead of resolution
            params["model"] = job_set_type
            params["quality"] = quality
            if seed is None:
                seed = random.randint(100000, 999999)
            params["seed"] = seed
        else:
            # Nano Banana / Flux / Kling use resolution
            params["resolution"] = resolution
            params["input_images"] = input_images or []

        if "nano-banana-pro" in model:
            params["is_storyboard"] = False
            params["is_zoom_control"] = False

        body: dict = {
            "params": params,
            "use_unlim": use_unlim,
        }

        if "seedream" not in model:
            body["use_seedream_bonus"] = use_seedream_bonus

        # Endpoint path
        if version == "v2":
            path = f"/jobs/v2/{url_slug}"
        else:
            path = f"/jobs/{url_slug}"

        resp = self._post(path, json=body)
        return GenerateResponse.from_api(resp)

    # ------------------------------------------------------------------
    # Job status & polling
    # ------------------------------------------------------------------

    def get_job_status(self, job_id: str) -> dict:
        """Quick status check for a job."""
        real_id = self._resolve_id(job_id)
        return self._get(f"/jobs/{real_id}/status")

    def get_job(self, job_id: str) -> Job:
        """Full job detail including image URLs."""
        real_id = self._resolve_id(job_id)
        resp = self._get(f"/jobs/{real_id}")
        job = Job.from_api(resp)
        if job_id.isdigit():
            job.display_num = int(job_id)
        return job

    def wait_for_jobs(
        self,
        job_ids: list[str],
        poll_interval: float = 2.0,
        timeout: float = 300,
        on_status: callable | None = None,
    ) -> list[Job]:
        """Poll until all jobs complete or timeout."""
        deadline = time.time() + timeout
        pending = set(job_ids)
        completed: dict[str, Job] = {}

        while pending and time.time() < deadline:
            for jid in list(pending):
                try:
                    status = self.get_job_status(jid)
                    state = status.get("status", "")

                    if on_status:
                        on_status(jid, state)

                    if state == "completed":
                        job = self.get_job(jid)
                        completed[jid] = job
                        pending.discard(jid)
                    elif state in ("failed", "error", "cancelled"):
                        pending.discard(jid)
                        completed[jid] = Job(id=jid, status=state)
                except Exception:
                    pass

            if pending:
                time.sleep(poll_interval)

        # Fetch remaining as-is
        for jid in pending:
            try:
                completed[jid] = self.get_job(jid)
            except Exception:
                completed[jid] = Job(id=jid, status="timeout")

        return [completed[jid] for jid in job_ids if jid in completed]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, model_types: list[str] | None = None, size: int = 20) -> list[Job]:
        """Get recent generation history."""
        if model_types is None:
            model_types = [m[1] for m in MODELS.values()]

        params = [("size", str(size))]
        for mt in model_types:
            params.append(("job_set_type", mt))

        query = "&".join(f"{k}={v}" for k, v in params)
        resp = self._get(f"/jobs/accessible?{query}")

        jobs = []
        for item in resp.get("jobs", []):
            job = Job.from_api(item)
            jobs.append(job)

        self._assign_display_nums(jobs)
        return jobs

    # ------------------------------------------------------------------
    # User & wallet
    # ------------------------------------------------------------------

    def get_user(self) -> UserInfo:
        resp = self._get("/user")
        return UserInfo.from_api(resp)

    def get_wallet(self) -> Wallet:
        resp = self._get("/workspaces/wallet")
        return Wallet.from_api(resp)

    def get_profile(self) -> dict:
        return self._get("/user/profile")

    def get_free_gens(self) -> dict:
        return self._get("/user/free-gens")

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_image(self, file_path: Path) -> dict:
        """Upload an image file and return media info for use in generation."""
        mime = "image/png"
        suffix = file_path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif suffix == ".webp":
            mime = "image/webp"

        # Step 1: Get presigned upload URL
        batch_resp = self._post("/media/batch", json={
            "mimetypes": [mime],
            "source": "user_upload",
        })
        if not batch_resp or not isinstance(batch_resp, list):
            raise HiggsError("Failed to get upload URL")
        media = batch_resp[0]
        media_id = media["id"]
        upload_url = media["upload_url"]
        media_url = media["url"]

        # Step 2: Upload to S3
        with open(file_path, "rb") as f:
            upload_resp = httpx.put(
                upload_url,
                content=f.read(),
                headers={"Content-Type": mime},
                timeout=60,
            )
        upload_resp.raise_for_status()

        # Step 3: Confirm upload
        self._post(f"/media/{media_id}/upload", json={
            "filename": file_path.name,
            "force_nsfw_check": True,
        })

        return {
            "data": {
                "id": media_id,
                "url": media_url,
                "type": "media_input",
            },
            "role": "image",
        }

    # ------------------------------------------------------------------
    # Asset detail
    # ------------------------------------------------------------------

    def get_asset_detail(self, job_id: str) -> Job:
        """Get asset detail (alternative to job detail)."""
        real_id = self._resolve_id(job_id)
        resp = self._get(f"/assets/{real_id}/detail")
        return Job.from_api(resp)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, **kwargs) -> dict:
        resp = self._client.get(path, **kwargs)
        return self._handle_response(resp)

    def _post(self, path: str, **kwargs):
        resp = self._client.post(path, **kwargs)
        return self._handle_response(resp)

    def _handle_response(self, resp: httpx.Response):
        if resp.status_code == 401:
            raise TokenExpiredError(
                "Token expired. Run: higgsfield login --with-token TOKEN"
            )
        if resp.status_code == 429:
            raise RateLimitError("Rate limit hit. Wait and try again.")
        if resp.status_code == 404:
            raise ResourceNotFoundError("Resource not found.")
        if resp.status_code == 402:
            raise InsufficientCreditsError("Not enough credits.")
        if resp.status_code == 403:
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                pass
            if "datadome" in resp.text.lower():
                raise HiggsError(
                    "Blocked by DataDome bot protection.\n"
                    "This usually happens with direct API calls.\n"
                    "Try refreshing your token: higgsfield login --with-token TOKEN"
                )
            raise HiggsError(f"Forbidden (403). {detail}")

        resp.raise_for_status()

        if not resp.content:
            return {}
        return resp.json()

    # ------------------------------------------------------------------
    # ID map (display number -> real UUID)
    # ------------------------------------------------------------------

    def _resolve_id(self, ref: str) -> str:
        if ref.isdigit():
            real = self._id_map.get(ref)
            if real:
                return real
            raise ResourceNotFoundError(
                f"No job found for #{ref}. Run 'higgsfield history' first."
            )
        return ref

    def _assign_display_nums(self, jobs: list[Job]) -> None:
        for job in jobs:
            existing = next(
                (k for k, v in self._id_map.items() if v == job.id), None
            )
            if existing:
                job.display_num = int(existing)
            else:
                job.display_num = self._next_num
                self._id_map[str(self._next_num)] = job.id
                self._next_num += 1

        self._trim_id_map()
        self._save_id_map()

    def _load_id_map(self) -> dict[str, str]:
        path = CACHE_DIR / "id_map.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_id_map(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / "id_map.json"
        path.write_text(json.dumps(self._id_map))

    def _trim_id_map(self) -> None:
        if len(self._id_map) > self.MAX_ID_MAP_SIZE:
            sorted_keys = sorted(self._id_map, key=lambda k: int(k) if k.isdigit() else 0)
            excess = len(self._id_map) - self.MAX_ID_MAP_SIZE
            for k in sorted_keys[:excess]:
                del self._id_map[k]
