import json
import logging
import os
import re
import shutil
import tempfile
import uuid

import azure.functions as func

from shared.script_parser import parse_storyboard
from shared.script_converter import convert_script_to_scenes
from shared.tts_client import synthesize_narration
from shared.video_composer import build_scene_clip_from_video, build_logo_outro, burn_text_overlay, render_final_video
from shared.video_client import generate_scene_video
from shared.blob_uploader import upload_video

# Small fixed pause appended after each scene's narration ends, so cuts
# don't feel instantaneous - this is the only "pause" added; we no longer
# stretch scenes out to match the storyboard's estimated timestamps, which
# is what caused long awkward silences before.
PAUSE_AFTER_NARRATION_SECONDS = 0.6

# Floor for scenes with no narration (e.g. music-only outro) - keeps them
# from collapsing to near-zero length.
MIN_SILENT_SCENE_SECONDS = 4.0

DEFAULT_LOGO_SUBTITLE = "Learn more with HelloAlfred"


def _extract_logo_subtitle(visual_prompt: str, default: str = DEFAULT_LOGO_SUBTITLE) -> str:
    """
    Storyboard visual prompts for the logo outro scene follow a loose
    convention like:
        "HelloAlfred logo. Text: Track your blood pressure daily. Soft fade."
    The intended on-screen subtitle is whatever follows "Text:", not the
    whole raw prompt - the rest is production direction (e.g. "Soft fade")
    that was never meant to be rendered as text. This works for any topic,
    not just AFib, so it replaces the old curriculum/learn-more special cases.
    """
    match = re.search(r"text\s*:\s*(.+?)(?:\.\s|\.$|$)", visual_prompt, re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        if extracted:
            return extracted
    return default


def _save_converted_script(raw_scenes: list, run_id: str) -> str:
    """Saves the structured scenes JSON into SCRIPT_JSON_DIR, one file per run."""
    script_json_dir = os.environ.get("SCRIPT_JSON_DIR")
    if not script_json_dir:
        return None
    os.makedirs(script_json_dir, exist_ok=True)
    json_path = os.path.join(script_json_dir, f"script_{run_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"scenes": raw_scenes}, f, indent=2)
    logging.info(f"Saved converted script to {json_path}")
    return json_path


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("GenerateVideo triggered.")

    try:
        body = req.get_json()
    except Exception:
        return func.HttpResponse(
            "Request body must be JSON with either a 'scenes' array or a 'script' string.",
            status_code=400,
        )

    run_id = uuid.uuid4().hex[:8]
    converted_script_path = None

    if "scenes" in body:
        raw_scenes = body["scenes"]
    elif "script" in body:
        logging.info("Raw script received - converting to structured scenes via LLM.")
        raw_scenes = convert_script_to_scenes(body["script"])
        logging.info(f"Converted script into {len(raw_scenes)} scenes.")
        converted_script_path = _save_converted_script(raw_scenes, run_id)
    else:
        return func.HttpResponse(
            "Request body must contain either a 'scenes' array or a 'script' string.",
            status_code=400,
        )

    scenes = parse_storyboard(raw_scenes)

    if body.get("preview_only"):
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "preview",
                    "scenes": raw_scenes,
                    "converted_script_path": converted_script_path,
                },
                indent=2,
            ),
            mimetype="application/json",
            status_code=200,
        )

    work_dir = tempfile.mkdtemp(prefix="afib_video_")
    scene_clips = []

    for scene in scenes:
        logging.info(f"Processing scene {scene.index}: {scene.visual_prompt[:60]}...")

        # 1. Synthesize narration first
        audio_path = os.path.join(work_dir, f"scene_{scene.index}.wav")
        narration_duration = synthesize_narration(scene.narration, audio_path)

        if scene.narration.strip():
            clip_duration = narration_duration + PAUSE_AFTER_NARRATION_SECONDS
        else:
            clip_duration = max(scene.duration_sec, MIN_SILENT_SCENE_SECONDS)

        # 2. Check if this is the logo outro scene (no narration + visual
        # mentions logo) — if so, render the real logo card instead of Sora.
        logo_svg = os.path.join(os.path.dirname(__file__), "..", "assets", "alfredlogo.svg")
        is_logo_scene = (
            not scene.narration.strip() and
            "logo" in scene.visual_prompt.lower() and
            os.path.exists(logo_svg)
        )

        if is_logo_scene:
            logging.info(f"Scene {scene.index}: rendering real HelloAlfred logo outro.")
            video_path = os.path.join(work_dir, f"scene_{scene.index}_logo.mp4")
            subtitle = _extract_logo_subtitle(scene.visual_prompt)
            build_logo_outro(
                logo_svg_path=os.path.normpath(logo_svg),
                output_path=video_path,
                duration=clip_duration,
                subtitle=subtitle,
            )
            from moviepy.editor import VideoFileClip, AudioFileClip
            raw_clip = VideoFileClip(video_path)
            audio = AudioFileClip(audio_path)
            clip = raw_clip.set_audio(audio)

        else:
            # 3. Generate real animated Sora clip for all other scenes
            motion_prompt = scene.visual_prompt
            if scene.visual_prompt_end:
                motion_prompt = (
                    f"{scene.visual_prompt} Over the course of the clip, it transitions to: "
                    f"{scene.visual_prompt_end}"
                )
            motion_prompt += (
                " Style: clean flat medical-education illustration, soft color "
                "palette, no text overlays, no watermarks. Smooth, continuous motion "
                "throughout - nothing in the frame should be still."
            )

            video_path = os.path.join(work_dir, f"scene_{scene.index}_sora.mp4")
            generate_scene_video(motion_prompt, target_duration=clip_duration, output_path=video_path)

            # Burn on-screen label + description if this scene has them
            if scene.on_screen_label or scene.on_screen_description:
                logging.info(f"Scene {scene.index}: burning text overlay — '{scene.on_screen_label}'")
                overlaid_path = os.path.join(work_dir, f"scene_{scene.index}_overlay.mp4")
                burn_text_overlay(
                    input_path=video_path,
                    output_path=overlaid_path,
                    label=scene.on_screen_label,
                    description=scene.on_screen_description,
                )
                video_path = overlaid_path

            clip = build_scene_clip_from_video(video_path, audio_path, clip_duration)

        scene_clips.append(clip)

    # 4. Concatenate all scenes into the final video
    output_filename = f"afib_video_{run_id}.mp4"
    rendered_path = os.path.join(work_dir, output_filename)
    render_final_video(scene_clips, rendered_path)

    # 5. Copy the final video into the local output folder
    local_output_dir = os.environ.get("LOCAL_OUTPUT_DIR")
    final_local_path = None
    if local_output_dir:
        os.makedirs(local_output_dir, exist_ok=True)
        final_local_path = os.path.join(local_output_dir, output_filename)
        shutil.copy2(rendered_path, final_local_path)
        logging.info(f"Saved video to {final_local_path}")

    # 6. Optionally also upload to Blob Storage
    video_url = None
    if os.environ.get("UPLOAD_TO_BLOB", "false").lower() == "true":
        video_url = upload_video(rendered_path, output_filename)

    return func.HttpResponse(
        json.dumps(
            {
                "status": "success",
                "local_path": final_local_path,
                "video_url": video_url,
                "converted_script_path": converted_script_path,
            }
        ),
        mimetype="application/json",
        status_code=200,
    )