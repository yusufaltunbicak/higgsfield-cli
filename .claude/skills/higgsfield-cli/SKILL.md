---
name: higgsfield-cli
description: CLI skill for Higgsfield AI to generate, enhance, and manage AI images from the terminal using nano-banana, seedream, flux, and kling models
author: yusufaltunbicak
version: "0.1.0"
tags:
  - higgsfield
  - ai
  - image-generation
  - nano-banana
  - seedream
  - flux
  - kling
  - terminal
  - cli
---

# higgsfield-cli Skill

Use this skill when the user wants to generate AI images, enhance existing images, or manage their Higgsfield generation history from the terminal. Supports multiple models (Nano Banana Pro, Seedream, Flux, Kling), batch generation, image-to-image, upscale, relight, and outpaint.

## Prerequisites

```bash
# Install (requires Python 3.10+)
cd ~/higgsfield-cli && pip install -e .

# Optional: Chrome cookie extraction for auto-refresh
pip install -e ".[chrome]"
```

## Authentication

- First run: `higgsfield login` prompts for browser cookies.
- Tokens auto-refresh via Clerk API (no Chrome tab needed after first login).
- Token lifetime is 60 seconds; Clerk refresh extends this indefinitely.
- `HIGGSFIELD_TOKEN` env var is supported for CI/scripting.
- Token cached at `~/.cache/higgsfield-cli/token.json` with `chmod 600`.
- Generate commands require Chrome with higgsfield.ai tab open (DataDome protection on POST endpoints).

```bash
higgsfield login                          # Interactive cookie login
higgsfield login --with-token TOKEN       # Direct JWT (expires in 60s)
higgsfield whoami                         # Verify current user and credits
```

### Login Steps

1. Open `higgsfield.ai` in Chrome and log in
2. Open Console (`Cmd+Option+J`)
3. Type: `document.cookie`
4. Copy the output
5. Run `higgsfield login` and paste

After first login, read-only commands (history, credits, download, etc.) work indefinitely without Chrome. Generation commands need a higgsfield.ai tab open in Chrome.

## Command Reference

### Generate

```bash
higgsfield generate "a red apple on a white table"                      # Default: nano-banana-pro, 4k, 16:9, batch 4
higgsfield generate "sunset over mountains" -m seedream-v4.5 -q high    # Seedream model
higgsfield generate "portrait" -a 9:16 -b 2 --download                 # Portrait, 2 images, auto-download
higgsfield generate "logo design" -m nano-banana-flash -r 1k -b 1 -y   # Flash model, 1k, skip confirm
higgsfield generate "edit this" -A reference.png                        # With reference image
higgsfield generate "scene" -A img1.png -A img2.png                     # Multiple reference images
higgsfield generate "cube" --unlim                                      # Use unlimited mode
higgsfield generate "sky" --no-wait                                     # Submit and return immediately
higgsfield generate "art" -d -o ~/Pictures                              # Download to specific dir
```

### Models

| Model | Flag | Res/Quality | Notes |
|-------|------|-------------|-------|
| `nano-banana-pro` | `-m nano-banana-pro` | `-r 4k/2k/1k` | Default. Best quality. |
| `nano-banana-flash` | `-m nano-banana-flash` | `-r 4k/2k/1k` | Faster generation. |
| `seedream-v4.5` | `-m seedream-v4.5` | `-q high/basic` | Uses quality + seed. |
| `seedream-v5-lite` | `-m seedream-v5-lite` | `-q high/basic` | Lighter seedream. |
| `flux-2` | `-m flux-2` | `-r 4k/2k/1k` | Flux model. |
| `kling-o1` | `-m kling-o1` | `-r 4k/2k/1k` | Kling omni image. |

```bash
higgsfield models                                                       # List all available models
```

### Aspect Ratios

`1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `21:9`, `9:21`, `3:2`, `2:3`

### Enhancement

```bash
higgsfield upscale 1                                                    # Upscale job #1 to higher resolution
higgsfield upscale 1 --download -o ~/Pictures                           # Upscale and download
higgsfield relight 1                                                    # AI-adjusted lighting
higgsfield relight 1 -d -y                                              # Relight, download, skip confirm
higgsfield outpaint 1                                                   # Extend image borders (all directions)
higgsfield outpaint 1 --direction right                                 # Outpaint right only
higgsfield outpaint 1 --direction left --download                       # Outpaint left and download
```

### History

```bash
higgsfield history                                                      # Recent 20 jobs
higgsfield history --max 50                                             # More items
higgsfield history --model nano-banana-pro                              # Filter by model
```

### Status

```bash
higgsfield status 1                                                     # Check job #1 status
higgsfield status abc123-uuid                                           # By full UUID
```

### Download

```bash
higgsfield download 1 2 3                                               # Download multiple jobs
higgsfield download 1 -o ~/Pictures                                     # Custom output dir
higgsfield download 1 --thumbnail                                       # Download thumbnail instead
```

### Watch (Live Progress)

```bash
higgsfield watch 1 2 3                                                  # Watch specific jobs
higgsfield watch --all                                                  # Watch all pending jobs
higgsfield watch --all --download                                       # Watch and auto-download
higgsfield watch 1 --interval 5                                         # Custom poll interval
```

### Re-run & Reference

```bash
higgsfield again 1                                                      # Re-run job #1 with same settings
higgsfield again 1 --seed 42                                            # Override seed
higgsfield again 1 --download                                           # Re-run and download
higgsfield use 1 "make it more colorful"                                # Use job #1's image as reference
higgsfield use 1 "anime style" -m nano-banana-pro                       # Reference with different model
```

### Batch Generation

```bash
higgsfield batch prompts.txt                                            # One prompt per line
higgsfield batch prompts.txt --download -o ./output                     # Download all results
higgsfield batch ideas.txt -m seedream-v4.5 -q high                     # All with seedream
higgsfield batch prompts.txt --delay 5                                  # 5s between requests
```

File format: one prompt per line, `#` comments and empty lines ignored.

### Management

```bash
higgsfield open 1                                                       # Open image in browser
higgsfield delete 1 2 3                                                 # Delete jobs (with confirmation)
higgsfield delete 1 -y                                                  # Skip confirmation
higgsfield favorite 1                                                   # Toggle favorite
higgsfield favorite 1 2 3                                               # Toggle multiple
```

### Account

```bash
higgsfield credits                                                      # Show credit balance
higgsfield free-gens                                                    # Free generation counts per model
higgsfield whoami                                                       # User info + plan + credits
```

## JSON / Scripting

**Auto-JSON on pipe:** When stdout is piped (not a terminal), all commands automatically output JSON.

```bash
higgsfield history | jq '.data[0].prompt'                               # Auto-JSON when piped
higgsfield credits --json                                               # Explicit JSON in terminal
higgsfield history --json | jq '.data[] | select(.status == "completed")'
higgsfield status 1 --json | jq '.data.results.raw_url'
```

**Structured envelope:** All JSON output is wrapped in a standard envelope:

```json
{"ok": true, "schema_version": "1", "data": [...]}
```

Errors return structured JSON (when in JSON mode):

```json
{"ok": false, "error": {"code": "session_expired", "message": "..."}}
```

Error codes: `session_expired`, `not_authenticated`, `rate_limited`, `insufficient_credits`, `job_failed`, `not_found`, `unknown_error`.

### JSON Field Names

Job objects (`history`, `status` with `--json`):

| Field | Type | Example |
|-------|------|---------|
| `id` | string | UUID |
| `display_num` | int | `3` |
| `status` | string | `"completed"`, `"in_progress"`, `"failed"` |
| `job_set_type` | string | `"nano_banana_2"` |
| `prompt` | string | `"a red apple"` |
| `resolution` | string | `"4k"` |
| `quality` | string | `"high"` |
| `aspect_ratio` | string | `"16:9"` |
| `batch_size` | int | `4` |
| `width` | int | `5504` |
| `height` | int | `3072` |
| `seed` | int\|null | `42` or `null` |
| `results` | object\|null | `{"raw_url": "...", "min_url": "...", "type": "image"}` |
| `created_at` | float | Unix timestamp |
| `is_favourite` | bool | `false` |

## ID System

Jobs get short display numbers (#1, #2, #3...) mapped to real UUIDs. Numbers are assigned when listing history and persist across commands. ID map is capped at 200 entries (oldest evicted).

```bash
higgsfield history             # Shows #107, #108, #109...
higgsfield status 107          # Check job #107
higgsfield download 107 108    # Download by display number
higgsfield open 107            # Open in browser
higgsfield again 107           # Re-run with same settings
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `HIGGSFIELD_TOKEN` | Override bearer token (skip login) |
| `HIGGSFIELD_CLI_CACHE` | Cache directory (default: `~/.cache/higgsfield-cli`) |
| `HIGGSFIELD_CLI_CONFIG` | Config directory (default: `~/.config/higgsfield-cli`) |

## Configuration

Config file: `~/.config/higgsfield-cli/config.yaml`

```yaml
model: nano-banana-pro        # Default model
resolution: 4k                # Default resolution
quality: high                 # Default quality (seedream)
aspect_ratio: "16:9"          # Default aspect ratio
batch_size: 4                 # Default batch size
auto_download: false          # Auto-download completed images
output_dir: "."               # Default output directory
```

## Common Patterns for AI Agents

```bash
# Generate a single quick image
higgsfield generate "description here" -b 1 -y

# Generate and immediately download
higgsfield generate "scene description" -d -o ~/Downloads -y

# Check remaining credits before generating
higgsfield credits

# Generate with specific model and settings
higgsfield generate "corporate topology diagram" -m nano-banana-pro -r 4k -a 16:9 -b 4 -y

# Wait for all pending jobs to finish
higgsfield watch --all --download -o ~/Downloads

# Re-run a good result with different seed
higgsfield again 107 --download

# Use an existing image as reference for variations
higgsfield use 107 "same style but with blue background" -y -d

# Batch generate from a file of prompts
higgsfield batch prompts.txt -d -o ./output -y

# Download a specific completed job
higgsfield download 107 -o ~/Desktop

# Enhance an image: upscale, relight, or outpaint
higgsfield upscale 107 -d -y
higgsfield relight 107 -d -y
higgsfield outpaint 107 --direction right -d -y

# Check what free generations are available
higgsfield free-gens

# View history filtered by model
higgsfield history --model nano-banana-pro --max 10
```

## Error Handling

- Token expired -> auto-refresh via Clerk API (no Chrome needed).
- `No job found for #N` -> run `higgsfield history` first to populate the ID map.
- `Not enough credits` -> check with `higgsfield credits`, buy more at higgsfield.ai.
- `Forbidden (403)` -> DataDome protection on generate. Ensure Chrome is open with higgsfield.ai tab.
- HTTP 429 -> rate limit. Wait and retry.
- `Token expired. Run: higgsfield login` -> Clerk refresh failed. Re-login with `higgsfield login`.

## Safety Notes

- Token and cookies cached with `chmod 600` (owner-only read/write).
- Clerk client cookie saved separately for auto-refresh.
- `generate`, `again`, `use`, `batch`, `delete`, `upscale`, `relight`, `outpaint` ask for confirmation by default (use `-y` to skip).
- Chrome is never auto-launched; only used if already running.
- Do not share or log bearer tokens.
- Prefer `higgsfield login` over manually copying tokens.
