import os
from pathlib import Path

# API
API_BASE = "https://fnf.higgsfield.ai"
CLERK_BASE = "https://clerk.higgsfield.ai"

# CDN - output images (no auth needed)
IMAGE_CDN = "https://d8j0ntlcm91z4.cloudfront.net"

# CDN - user uploads (presigned URLs)
UPLOAD_CDN = "https://d276s3zg8h21b2.cloudfront.net"
MEDIA_CDN = "https://d2ol7oe51mr4n9.cloudfront.net"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Cache & config
CACHE_DIR = Path(os.environ.get(
    "HIGGSFIELD_CLI_CACHE",
    Path.home() / ".cache" / "higgsfield-cli",
))
CONFIG_DIR = Path(os.environ.get(
    "HIGGSFIELD_CLI_CONFIG",
    Path.home() / ".config" / "higgsfield-cli",
))
TOKEN_FILE = CACHE_DIR / "token.json"
COOKIE_FILE = CACHE_DIR / "cookies.json"

# Model registry: UI name -> (url_slug, job_set_type, endpoint_version)
MODELS = {
    "nano-banana-pro": ("nano-banana-2", "nano_banana_2", "v1"),
    "nano-banana-flash": ("nano_banana_flash", "nano_banana_flash", "v2"),
    "seedream-v4.5": ("seedream-v4-5", "seedream_v4_5", "v1"),
    "seedream-v5-lite": ("seedream-v5-lite", "seedream_v5_lite", "v1"),
    "flux-2": ("flux-2", "flux_2", "v1"),
    "kling-o1": ("kling-omni-image", "kling_omni_image", "v1"),
}

DEFAULT_MODEL = "nano-banana-pro"

# Aspect ratios with default dimensions (sent in request, server recalculates)
ASPECT_RATIOS = {
    "1:1": (1024, 1024),
    "16:9": (5504, 3072),
    "9:16": (3072, 5504),
    "4:3": (4800, 3584),
    "3:4": (3584, 4800),
    "21:9": (6336, 2688),
    "9:21": (2688, 6336),
    "3:2": (4800, 3200),
    "2:3": (3200, 4800),
}

# Resolution options
RESOLUTIONS = ("4k", "2k", "1k")

# Quality options (seedream models)
QUALITIES = ("high", "basic")
