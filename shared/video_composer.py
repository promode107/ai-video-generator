"""
video_composer.py
Handles all video assembly:
- burn_text_overlay: burns label/description onto a Sora clip via ffmpeg drawtext
- build_scene_clip_from_video: wraps a Sora MP4 + narration WAV into a scene clip
- render_final_video: concatenates all scene clips into the final MP4
"""

import logging
import os
import subprocess
import tempfile
import textwrap
import shutil as _shutil

from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    concatenate_videoclips,
)
import moviepy.video.fx.all as vfx


def _ensure_fontconfig_file() -> str:
    """
    The gyan.dev ffmpeg Windows build is compiled with fontconfig support,
    and drawtext initializes fontconfig at filter-init time even when an
    explicit `fontfile` is given. Without a valid fonts.conf on the system,
    that init fails outright ("Fontconfig error: Cannot load default config
    file") and aborts the whole filtergraph - nothing to do with filter
    syntax. Point fontconfig at a minimal config that just references the
    Windows Fonts folder, generated once and cached in the temp dir.
    """
    conf_dir = os.path.join(tempfile.gettempdir(), "helloalfred_fontconfig")
    conf_path = os.path.join(conf_dir, "fonts.conf")
    if not os.path.exists(conf_path):
        os.makedirs(conf_dir, exist_ok=True)
        cache_dir = os.path.join(conf_dir, "cache").replace("\\", "/")
        fonts_conf = (
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
            '<fontconfig>\n'
            '  <dir>C:/Windows/Fonts</dir>\n'
            f'  <cachedir>{cache_dir}</cachedir>\n'
            '</fontconfig>\n'
        )
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(fonts_conf)
    return conf_path


def burn_text_overlay(input_path: str, output_path: str,
                      label: str, description: str) -> str:
    """
    Burns a clean, readable label + description onto a video clip using
    ffmpeg's drawtext filter, tuned for patients reading medical content:

    - Description text wraps across up to 2 lines instead of running off
      the frame or getting silently truncated.
    - A soft multi-band gradient scrim sits behind the text instead of one
      flat black box, so it reads as a gentle fade rather than a hard edge
      cutting across the scene.
    - Label and description have a clear size/weight hierarchy (bold label,
      lighter description) so the key term is scannable at a glance, with
      a small brand-accent rule marking the label as the "headline."
    """
    label_esc = label.strip()

    brand_accent = (4, 193, 214)  # HelloAlfred cyan, matches the logo mark

    # Get frame dimensions so the overlay PNG matches exactly.
    probe_clip = VideoFileClip(input_path)
    width, height = probe_clip.size
    probe_clip.close()

    def _load_font(paths, size):
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    bold_font = _load_font(
        ["C:/Windows/Fonts/segoeuisb.ttf", "C:/Windows/Fonts/arialbd.ttf"],
        size=int(height / 16),
    )
    regular_font = _load_font(
        ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"],
        size=int(height / 24),
    )

    # Wrap the description across up to 2 lines - this is the part patients
    # actually need to read and understand, so nothing should get cut off
    # or spill past the edges of the frame.
    desc_lines = textwrap.wrap(description.strip(), width=42)[:2]

    # Scrim starts higher up the frame (and the whole text block sits higher)
    # when there are 2 description lines, so text never crowds the very
    # bottom edge of the video.
    if len(desc_lines) == 2:
        scrim_top = 0.68
        label_y = 0.735
        desc_ys = [0.805, 0.865]
    else:
        scrim_top = 0.76
        label_y = 0.815
        desc_ys = [0.885]

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Soft gradient scrim: several stacked bars of increasing opacity
    # instead of one flat block, so it fades in gently rather than cutting
    # a hard edge across the animation. Bands are non-overlapping, so plain
    # rectangle fills (no alpha_composite needed) render this correctly.
    band_count = 6
    band_h = (1.0 - scrim_top) / band_count
    for i in range(band_count):
        y0 = int((scrim_top + i * band_h) * height)
        y1 = int((scrim_top + (i + 1) * band_h) * height)
        alpha = 0.10 + (0.58 - 0.10) * (i / (band_count - 1))
        draw.rectangle([0, y0, width, y1], fill=(0, 0, 0, int(alpha * 255)))

    # Small accent rule above the label - marks it as the headline term.
    accent_w = int(width * 0.06)
    accent_h = max(2, int(height * 0.006))
    accent_y = int((label_y - 0.045) * height)
    draw.rectangle(
        [(width - accent_w) // 2, accent_y,
         (width + accent_w) // 2, accent_y + accent_h],
        fill=brand_accent + (int(0.9 * 255),),
    )

    def _draw_centered(text, y_frac, font, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = int(y_frac * height)
        # Soft shadow for legibility over varied backgrounds, matching the
        # original drawtext shadowcolor/shadowx/shadowy look.
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 128))
        draw.text((x, y), text, font=font, fill=fill)

    _draw_centered(label_esc, label_y, bold_font, (255, 255, 255, 255))
    for line, y_frac in zip(desc_lines, desc_ys):
        _draw_centered(line, y_frac, regular_font, (255, 255, 255, int(0.92 * 255)))

    overlay_png_path = output_path.replace(".mp4", "_overlay.png")
    overlay.save(overlay_png_path)

    ffmpeg_bin = _shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg_bin, "-y",
        "-i", input_path,
        "-i", overlay_png_path,
        "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        output_path,
    ]
    env = os.environ.copy()
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        debug_path = os.path.join(tempfile.gettempdir(), "ffmpeg_drawtext_error.log")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(f"RETURNCODE: {result.returncode}\n\n")
            f.write("CMD:\n" + " ".join(cmd) + "\n\nSTDERR:\n" + result.stderr)
        raise RuntimeError(
            f"ffmpeg overlay failed (code {result.returncode}) — full log at {debug_path}\n{result.stderr[-2000:]}"
        )
    try:
        os.remove(overlay_png_path)
    except OSError:
        pass
    return output_path



def build_logo_outro(logo_svg_path: str, output_path: str, duration: float,
                      subtitle: str = "Learn more in your AFib curriculum — 18 lessons",
                      width: int = 1280, height: int = 720) -> str:
    """
    Renders the HelloAlfred logo onto a clean white card as a proper outro,
    instead of asking Sora to hallucinate the logo.

    Steps:
    1. Convert SVG → PNG (via cairosvg or Inkscape; falls back to a plain
       white card if neither is available)
    2. Composite logo + subtitle text onto a 1280×720 white background (PIL)
    3. Write a video from that still frame with a fade-in/out using ffmpeg
    """
    import subprocess
    import shutil as _shutil
    import os
    from PIL import Image, ImageDraw, ImageFont

    # ── 1. Convert SVG → PNG ─────────────────────────────────────────────────
    logo_png = output_path.replace(".mp4", "_logo.png")
    svg_converted = False

    # Try cairosvg first (pip install cairosvg)
    try:
        import cairosvg
        cairosvg.svg2png(url=logo_svg_path, write_to=logo_png, scale=4.0)
        svg_converted = True
        logging.info(f"build_logo_outro: SVG converted via cairosvg -> {logo_png}")
    except Exception as e:
        logging.warning(f"build_logo_outro: cairosvg conversion failed ({e}); trying Inkscape fallback.")

    # Fall back to Inkscape if installed
    if not svg_converted:
        inkscape = _shutil.which("inkscape")
        if inkscape:
            result = subprocess.run(
                [inkscape, "--export-type=png", f"--export-filename={logo_png}",
                 "--export-dpi=192", logo_svg_path],
                capture_output=True
            )
            if result.returncode == 0:
                svg_converted = True
                logging.info(f"build_logo_outro: SVG converted via Inkscape -> {logo_png}")
            else:
                logging.warning(f"build_logo_outro: Inkscape export failed: {result.stderr}")
        else:
            logging.warning("build_logo_outro: Inkscape not found on PATH either.")

    if not svg_converted:
        logging.error(
            "build_logo_outro: SVG conversion failed via both cairosvg and Inkscape — "
            "falling back to plain PIL text logo. Install cairosvg's native Cairo "
            "dependency (GTK runtime on Windows) or install Inkscape and add it to PATH."
        )

    import textwrap

    def _load_font(font_paths, size):
        """Try a list of candidate font files in order, falling back to
        PIL's tiny built-in bitmap font only if none are found."""
        for path in font_paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # ── 2. Composite onto white card (PIL) ───────────────────────────────────
    card = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    brand_accent = (4, 193, 214)      # HelloAlfred cyan, matches the logo mark
    subtitle_color = (55, 64, 74)     # dark slate — reads as confident copy, not a caption

    logo_fallback_font = _load_font(
        ["C:/Windows/Fonts/segoeuisb.ttf", "C:/Windows/Fonts/arialbd.ttf"],
        size=int(height * 0.09),
    )

    if svg_converted and os.path.exists(logo_png):
        logo_img = Image.open(logo_png).convert("RGBA")
        # Scale logo to ~35% of card width
        target_w = int(width * 0.35)
        ratio = target_w / logo_img.width
        target_h = int(logo_img.height * ratio)
        logo_img = logo_img.resize((target_w, target_h), Image.LANCZOS)
        # Center horizontally, place in upper-middle of card
        logo_x = (width - target_w) // 2
        logo_y = int(height * 0.30)
        card.paste(logo_img, (logo_x, logo_y), logo_img)
    else:
        # SVG conversion unavailable — draw fallback text logo
        draw.text((width // 2, int(height * 0.38)), "HelloAlfred",
                  fill=brand_accent, anchor="mm",
                  font=logo_fallback_font)

    # Small centered accent rule between the logo and the subtitle — a light
    # design touch so the subtitle reads as intentional copy, not a caption.
    rule_y = int(height * 0.555)
    rule_half_w = int(width * 0.035)
    draw.line(
        [(width // 2 - rule_half_w, rule_y), (width // 2 + rule_half_w, rule_y)],
        fill=brand_accent, width=3,
    )

    # Subtitle: real weighted font, brand-adjacent color, wrapped across up
    # to two lines so longer copy doesn't run off the card edges.
    subtitle_font = _load_font(
        ["C:/Windows/Fonts/segoeuisb.ttf", "C:/Windows/Fonts/calibrib.ttf",
         "C:/Windows/Fonts/arialbd.ttf"],
        size=int(height * 0.05),
    )
    wrapped_lines = textwrap.fill(subtitle, width=34).split("\n")[:2]
    line_height = int(height * 0.065)
    start_y = int(height * 0.62)
    for i, line in enumerate(wrapped_lines):
        draw.text((width // 2, start_y + i * line_height), line,
                  fill=subtitle_color, anchor="mm", font=subtitle_font)

    card_path = output_path.replace(".mp4", "_card.png")
    card.save(card_path)

    # ── 3. Render still card → video with fade in/out (ffmpeg) ───────────────
    ffmpeg_bin = _shutil.which("ffmpeg") or "ffmpeg"
    fade_dur = min(0.8, duration / 4)

    cmd = [
        ffmpeg_bin, "-y",
        "-loop", "1",
        "-i", card_path,
        "-vf", (
            f"fade=t=in:st=0:d={fade_dur},"
            f"fade=t=out:st={duration - fade_dur}:d={fade_dur}"
        ),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg logo outro failed:\n{result.stderr}")

    return output_path


def build_scene_clip_from_video(video_path: str, narration_wav_path: str,
                                 duration: float):
    """
    Wraps a Sora-generated MP4 as a scene clip matched to narration duration,
    with the narration audio attached.

    If the Sora clip is longer than needed: trim it.
    If the Sora clip is shorter than needed (narration ran long): slow the
    video playback speed so it stretches to fill the duration rather than
    freezing on the last frame — motion continues throughout, just slower.
    """
    raw_clip = VideoFileClip(video_path)

    if raw_clip.duration >= duration:
        video = raw_clip.subclip(0, duration)
    else:
        # Slow the clip down to fill the narration duration.
        # fx.speedx(factor < 1) stretches playback time.
        speed_factor = raw_clip.duration / duration
        video = raw_clip.fx(vfx.speedx, speed_factor)
        video = video.subclip(0, duration)

    audio = AudioFileClip(narration_wav_path)
    return video.set_audio(audio)


def render_final_video(scene_clips: list, output_path: str, fps: int = 30):
    """Concatenates all scene clips in order and writes the final MP4."""
    final = concatenate_videoclips(scene_clips, method="compose")
    final.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
    )
    return output_path