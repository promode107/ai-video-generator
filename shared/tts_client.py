"""
tts_client.py
Synthesizes narration audio per scene using Azure Cognitive Services Speech.

Uses SSML (not plain speak_text) so we can insert explicit pauses after
sentence-ending punctuation and commas - Azure's default TTS pacing barely
pauses at punctuation otherwise, which is what made narration feel rushed
with no breathing room between clauses/sentences.
"""

import os
import re
import wave
import struct
from xml.sax.saxutils import escape as xml_escape
import azure.cognitiveservices.speech as speechsdk

# Pause lengths inserted at different punctuation marks. Tuned for natural
# speech pacing - sentence-ending punctuation gets a longer break than a
# comma, which gets a brief one.
SENTENCE_BREAK_MS = 450
COMMA_BREAK_MS = 200


def _write_silent_wav(output_wav_path: str, duration_sec: float, sample_rate: int = 16000) -> float:
    """
    Writes a silent WAV file of the given duration. Used for scenes with no
    narration (e.g. music-only outro) so the video pipeline still has a
    valid audio track to read.
    """
    n_frames = int(duration_sec * sample_rate)
    with wave.open(output_wav_path, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        silence_frame = struct.pack("<h", 0)
        wav_file.writeframes(silence_frame * n_frames)
    return duration_sec


def _build_ssml(text: str, voice_name: str) -> str:
    """
    Converts plain narration text into SSML with explicit <break> tags
    after commas and sentence-ending punctuation, so the narration has
    natural breathing room instead of running clauses together.
    """
    escaped = xml_escape(text.strip())

    # Insert a break after sentence enders (. ! ?), keeping the punctuation.
    escaped = re.sub(
        r'([.!?])(\s+)',
        rf'\1<break time="{SENTENCE_BREAK_MS}ms"/>\2',
        escaped,
    )
    # Insert a shorter break after commas.
    escaped = re.sub(
        r'(,)(\s+)',
        rf'\1<break time="{COMMA_BREAK_MS}ms"/>\2',
        escaped,
    )

    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice_name}">{escaped}</voice>'
        '</speak>'
    )


def synthesize_narration(text: str, output_wav_path: str, fallback_duration: float = 4.0) -> float:
    """
    Synthesizes `text` to a WAV file at `output_wav_path`.
    Returns the resulting audio duration in seconds (used to drive how long
    the scene's video clip should be).

    If `text` is empty/whitespace-only (e.g. a music-only scene), writes a
    silent WAV of `fallback_duration` seconds instead of calling Azure Speech,
    which errors out on empty input.
    """
    if not text or not text.strip():
        return _write_silent_wav(output_wav_path, fallback_duration)

    speech_config = speechsdk.SpeechConfig(
        subscription=os.environ["SPEECH_KEY"],
        region=os.environ["SPEECH_REGION"],
    )
    voice_name = os.environ["SPEECH_VOICE_NAME"]
    speech_config.speech_synthesis_voice_name = voice_name

    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_wav_path)
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config
    )

    ssml = _build_ssml(text, voice_name)
    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(f"TTS failed: {result.reason} - {result.cancellation_details}")

    # duration is reported in 100-nanosecond units
    return result.audio_duration.total_seconds()