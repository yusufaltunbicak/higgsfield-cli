"""Dataclasses for Higgsfield API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ImageResult:
    raw_url: str = ""
    min_url: str = ""
    type: str = "image"

    @classmethod
    def from_api(cls, data: dict | None) -> ImageResult | None:
        if not data:
            return None
        raw = data.get("raw", {})
        min_ = data.get("min", {})
        return cls(
            raw_url=raw.get("url", ""),
            min_url=min_.get("url", ""),
            type=raw.get("type", "image"),
        )


@dataclass
class Job:
    id: str = ""
    status: str = ""
    job_set_type: str = ""
    job_set_id: str = ""
    prompt: str = ""
    resolution: str = ""
    quality: str = ""
    aspect_ratio: str = ""
    batch_size: int = 1
    width: int = 0
    height: int = 0
    seed: int | None = None
    results: ImageResult | None = None
    created_at: float = 0
    user_id: str = ""
    is_favourite: bool = False
    display_num: int = 0

    @property
    def created_dt(self) -> datetime:
        return datetime.fromtimestamp(self.created_at, tz=timezone.utc)

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def download_url(self) -> str:
        if self.results:
            return self.results.raw_url
        return ""

    @classmethod
    def from_api(cls, data: dict) -> Job:
        params = data.get("params", {})
        return cls(
            id=data.get("id", ""),
            status=data.get("status", ""),
            job_set_type=data.get("job_set_type", ""),
            job_set_id=data.get("job_set_id", ""),
            prompt=params.get("prompt", ""),
            resolution=params.get("resolution", ""),
            quality=params.get("quality", ""),
            aspect_ratio=params.get("aspect_ratio", ""),
            batch_size=params.get("batch_size", 1),
            width=params.get("width", 0),
            height=params.get("height", 0),
            seed=params.get("seed"),
            results=ImageResult.from_api(data.get("results")),
            created_at=data.get("created_at", 0),
            user_id=data.get("user_id", ""),
            is_favourite=data.get("is_favourite", False),
        )


@dataclass
class JobSet:
    id: str = ""
    type: str = ""
    project_id: str = ""
    created_at: float = 0
    params: dict = field(default_factory=dict)
    jobs: list[Job] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict) -> JobSet:
        jobs = [Job.from_api(j) for j in data.get("jobs", [])]
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            project_id=data.get("project_id", ""),
            created_at=data.get("created_at", 0),
            params=data.get("params", {}),
            jobs=jobs,
        )


@dataclass
class GenerateResponse:
    workspace_id: str = ""
    job_sets: list[JobSet] = field(default_factory=list)
    has_more: bool = False

    @property
    def all_job_ids(self) -> list[str]:
        ids = []
        for js in self.job_sets:
            for j in js.jobs:
                ids.append(j.id)
        return ids

    @classmethod
    def from_api(cls, data: dict) -> GenerateResponse:
        return cls(
            workspace_id=data.get("id", ""),
            job_sets=[JobSet.from_api(js) for js in data.get("job_sets", [])],
            has_more=data.get("has_more", False),
        )


@dataclass
class UserInfo:
    id: str = ""
    plan_type: str = ""
    subscription_credits: float = 0
    package_credits: float = 0
    daily_credits: float = 0
    total_plan_credits: int = 0
    billing_period: str = ""
    plan_ends_at: str = ""

    @property
    def total_credits(self) -> float:
        return self.subscription_credits + self.package_credits + self.daily_credits

    @classmethod
    def from_api(cls, data: dict) -> UserInfo:
        return cls(
            id=data.get("id", ""),
            plan_type=data.get("plan_type", ""),
            subscription_credits=data.get("subscription_credits", 0),
            package_credits=data.get("package_credits", 0),
            daily_credits=data.get("daily_credits", 0),
            total_plan_credits=data.get("total_plan_credits", 0),
            billing_period=data.get("billing_period", ""),
            plan_ends_at=data.get("plan_ends_at", ""),
        )


@dataclass
class Wallet:
    workspace_id: str = ""
    credits_balance: int = 0
    subscription_balance: int = 0
    total_credits: int = 0

    @property
    def credits_display(self) -> float:
        """subscription_balance is in hundredths."""
        return self.subscription_balance / 100

    @classmethod
    def from_api(cls, data: dict) -> Wallet:
        return cls(
            workspace_id=data.get("workspace_id", ""),
            credits_balance=data.get("credits_balance", 0),
            subscription_balance=data.get("subscription_balance", 0),
            total_credits=data.get("total_credits", 0),
        )
