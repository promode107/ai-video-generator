"""
script_converter.py
Converts a raw, free-form script (narration text + storyboard description,
in whatever shape the writer handed it over) into the structured
{"scenes": [...]} JSON that script_parser.py expects.

This lets the user paste/upload the kind of script they actually write
(prose narration + a scene-by-scene visual/audio table) instead of having
to hand-author JSON.
"""

import json
import os
from openai import AzureOpenAI


SYSTEM_PROMPT = """You convert video scripts into structured scene JSON.

You will be given a raw script that contains narration text and a
storyboard description (often as a markdown table with columns like
Scene, Time, Visual, Audio, Alt-Text).

Output ONLY a JSON object with this exact shape, nothing else - no markdown
fences, no commentary:

{
  "scenes": [
    {
      "scene": 1,
      "start": "0:00",
      "end": "0:12",
      "visual": "description of the START state of what should be shown on screen",
      "needs_motion": true,
      "visual_end": "description of the END state, ONLY if needs_motion is true, otherwise omit this field",
      "audio": "the exact narration line spoken during this scene",
      "alt_text": "accessibility description of the visual",
      "on_screen_label": "Short anatomical or conceptual label (2-4 words max), e.g. 'SA Node' or 'Blood Clot Forming'",
      "on_screen_description": "One short sentence explaining what is happening in the visual, e.g. 'Sends the electrical signal that starts each heartbeat'"
    }
  ]
}

Rules:
- "start" and "end" must be timestamps in "m:ss" or "h:mm:ss" format, taken
  directly from the script if given. If no timestamps exist, estimate them
  assuming an average narration pace of ~150 words per minute per scene,
  starting at 0:00 and accumulating.
- "audio" should be the narration text for that scene only, in plain text
  (no quotation marks added).
- If a scene has no narration (e.g. music-only outro), set "audio" to "".
- Preserve the original scene order.
- Do not invent extra scenes or merge scenes that were listed separately.
- "needs_motion": set true ONLY when the scene's visual description implies
  something changing or moving over the course of the scene (e.g. a counter
  changing value, sparks firing erratically, a heart speeding up, a clot
  traveling somewhere, an icon appearing). Set false for static cards,
  logos, title text, or scenes where nothing in the content itself changes.
- When "needs_motion" is true, "visual_end" must describe the END state of
  that same scene, written so the image stays visually consistent with
  "visual": same illustration style, same camera angle, same background and
  color palette as "visual" - describe ONLY what is different at the end.
- When "needs_motion" is false, omit "visual_end" entirely.
- "on_screen_label": a very short label (2-5 words) naming the key anatomical
  structure, medical concept, or action being shown in this scene.
  e.g. "SA Node", "Atrial Fibrillation", "Blood Clot", "Rate Control Medication".
  For transition/logo/outro scenes with no medical content, set to "".
- "on_screen_description": one short plain-English sentence (max 12 words)
  explaining what is happening visually in this scene, written for a patient
  with no medical background. e.g. "Sends the electrical signal that starts
  each heartbeat." For transition/logo/outro scenes, set to "".
"""


def get_chat_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ["OPENAI_API_VERSION"],
    )


def convert_script_to_scenes(raw_script: str) -> list:
    """
    Sends the raw script to the chat deployment and returns the parsed
    list of scene dicts (the same shape script_parser.parse_storyboard expects).
    """
    client = get_chat_client()
    deployment = os.environ["OPENAI_DEPLOYMENT_NAME"]

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_script},
        ],
        temperature=0,
    )

    content = response.choices[0].message.content.strip()

    # Defensive: strip markdown fences if the model added them anyway
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model did not return valid JSON. Raw output:\n{content}"
        ) from e

    if "scenes" not in parsed or not isinstance(parsed["scenes"], list):
        raise ValueError(f"Converted JSON missing 'scenes' array: {parsed}")

    return parsed["scenes"]