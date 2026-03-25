"""Structured exception hierarchy for higgsfield-cli."""

from __future__ import annotations


class HiggsError(Exception):
    """Base exception for all higgsfield-cli errors."""


class TokenExpiredError(HiggsError):
    """JWT token expired - needs refresh or re-login."""


class AuthRequiredError(HiggsError):
    """No token available - user must run 'higgsfield login'."""


class RateLimitError(HiggsError):
    """429 - API rate limit hit."""


class InsufficientCreditsError(HiggsError):
    """Not enough credits to generate."""


class JobFailedError(HiggsError):
    """Image generation job failed."""


class ResourceNotFoundError(HiggsError):
    """Job, image, or resource not found."""


def error_code_for_exception(exc: Exception) -> str:
    mapping = {
        TokenExpiredError: "session_expired",
        AuthRequiredError: "not_authenticated",
        RateLimitError: "rate_limited",
        InsufficientCreditsError: "insufficient_credits",
        JobFailedError: "job_failed",
        ResourceNotFoundError: "not_found",
    }
    return mapping.get(type(exc), "unknown_error")
