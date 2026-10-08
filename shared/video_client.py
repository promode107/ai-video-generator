"""
video_client.py
Wraps calls to the Azure OpenAI Sora 2 video generation deployment.
Generates a short animated clip per scene instead of a static image.

IMPORTANT: sora-2 deployments use a different API shape than the older
"sora" deployment type. The legacy endpoint
  POST /openai/v1/video/generations/jobs
only recognizes deployments literally named "sora" (now deprecated) and
returns 404 for sora-2 deployments regardless of deployment name. sora-2
must use the newer OpenAI-v1-aligned endpoint:
  POST /openai/v1/videos
  GET  /openai/v1/videos/{video_id}
  GET  /openai/v1/videos/{video_id}/content
with "size" (combined "WIDTHxHEIGHT" string) and "seconds" (string) instead
of separate width/height/n_seconds fields.

Includes automatic retry/backoff for 429 (rate limit) responses, since
Sora deployments are capped at a fixed requests-per-minute quota.
"""

import os
import time
import requests

POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 300
MAX_RETRIES = 5

# sora-2 public preview duration support has shifted across API versions and
# isn't fully settled in public docs as of this writing. 16 was tested and
# rejected with a 400 on this deployment - sticking to the confirmed-working
# values. If you get a 400 mentioning "seconds" again, check the Foundry
# playground for your specific deployment's allowed values.
SUPPORTED_DURATIONS = [4, 8, 12]

# statuses observed across Azure's preview rollout - check all of them
# since the exact wording has shifted as the API evolved
SUCCESS_STATUSES = {"succeeded", "completed"}
FAILURE_STATUSES = {"failed", "error"}


def _get_config():
    endpoint = os.environ["AZURE_OPENAI_VIDEO_ENDPOINT"].rstrip("/")
    api_key = os.environ["AZURE_OPENAI_VIDEO_KEY"]
    deployment_name = os.environ["VIDEO_DEPLOYMENT_NAME"]
    api_version = os.environ.get("VIDEO_API_VERSION", "preview")
    return endpoint, api_key, deployment_name, api_version


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """
    Wraps requests.get/post with automatic retry on 429 (rate limited).
    Respects the Retry-After header if Azure sends one; otherwise falls
    back to a doubling wait time (1s, 2s, 4s, 8s, 16s).
    """
    wait_seconds = 1
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.request(method, url, **kwargs)

        if response.status_code != 429:
            return response

        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else wait_seconds
        print(f"  Rate limited (429). Waiting {delay}s before retry {attempt}/{MAX_RETRIES}...")
        time.sleep(delay)
        wait_seconds *= 2

    return requests.request(method, url, **kwargs)


def _nearest_supported_duration(target_seconds: float) -> int:
    for d in SUPPORTED_DURATIONS:
        if d >= target_seconds:
            return d
    return SUPPORTED_DURATIONS[-1]


def _create_video_job(prompt: str, width: int, height: int, n_seconds: int) -> str:
    endpoint, api_key, deployment_name, api_version = _get_config()

    # New sora-2 endpoint: /openai/v1/videos (NOT /openai/v1/video/generations/jobs)
    url = f"{endpoint}/openai/v1/videos?api-version={api_version}"
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "model": deployment_name,
        "prompt": prompt,
        "size": f"{width}x{height}",
        "seconds": str(n_seconds),
    }

    response = _request_with_retry("POST", url, headers=headers, json=payload, timeout=30)
    print("Create job - status:", response.status_code)
    print("Create job - body:", response.text)
    response.raise_for_status()
    data = response.json()
    # sora-2's v1 schema returns the video's own id directly (e.g. "video_...")
    # rather than a separate job id - use whichever key is present.
    return data.get("id")


def _poll_job_until_done(video_id: str) -> dict:
    endpoint, api_key, _, api_version = _get_config()
    url = f"{endpoint}/openai/v1/videos/{video_id}?api-version={api_version}"
    headers = {"api-key": api_key}

    elapsed = 0
    while elapsed < MAX_WAIT_SECONDS:
        response = _request_with_retry("GET", url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        status = data.get("status")

        print(f"  Video {video_id} status: {status} ({elapsed}s elapsed)")

        if status in SUCCESS_STATUSES:
            return data
        elif status in FAILURE_STATUSES:
            raise RuntimeError(f"Sora video generation failed: {data}")

        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

    raise TimeoutError(f"Video generation did not finish within {MAX_WAIT_SECONDS}s.")


def _download_video(video_id: str, output_path: str) -> str:
    endpoint, api_key, _, api_version = _get_config()
    url = f"{endpoint}/openai/v1/videos/{video_id}/content?api-version={api_version}"
    headers = {"api-key": api_key}
    response = _request_with_retry("GET", url, headers=headers, timeout=60)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)
    return output_path


def generate_scene_video(prompt: str, target_duration: float, output_path: str,
                          width: int = 1280, height: int = 720) -> str:
    n_seconds = _nearest_supported_duration(target_duration)
    video_id = _create_video_job(prompt, width, height, n_seconds)
    if not video_id:
        raise RuntimeError("No video id returned from create-job call.")
    job_data = _poll_job_until_done(video_id)
    return _download_video(video_id, output_path)