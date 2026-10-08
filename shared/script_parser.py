"""
script_parser.py
Converts an incoming storyboard payload into a list of normalized Scene objects.

Expected input JSON shape (one entry per row of your storyboard table):
[
  {
    "scene": 1,
    "start": "0:00",
    "end": "0:12",
    "visual": "Animated heart with glowing SA node pulsing steadily...",
    "audio": "Your heart has its own electrical system - like a conductor leading an orchestra.",
    "alt_text": "A heart diagram shows a small node at the top right glowing rhythmically."
  },
  ...
]
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Scene:
    index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    visual_prompt: str
    narration: str
    alt_text: str
    needs_motion: bool = False
    visual_prompt_end: str = ""
    on_screen_label: str = ""
    on_screen_description: str = ""


def _timestamp_to_seconds(ts: str) -> float:
    """Converts 'm:ss' or 'h:mm:ss' into total seconds."""
    parts = [int(p) for p in ts.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def parse_storyboard(raw_scenes: List[dict]) -> List[Scene]:
    scenes = []
    for row in raw_scenes:
        start = _timestamp_to_seconds(row["start"])
        end = _timestamp_to_seconds(row["end"])
        scenes.append(
            Scene(
                index=int(row.get("scene", len(scenes) + 1)),
                start_sec=start,
                end_sec=end,
                duration_sec=max(end - start, 1.0),
                visual_prompt=row["visual"].strip(),
                narration=row.get("audio", "").strip(),
                alt_text=row.get("alt_text", "").strip(),
                needs_motion=bool(row.get("needs_motion", False)),
                visual_prompt_end=row.get("visual_end", "").strip(),
                on_screen_label=row.get("on_screen_label", "").strip(),
                on_screen_description=row.get("on_screen_description", "").strip(),
            )
        )
    return scenes