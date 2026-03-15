"""Generate voiceover (Piper TTS) and background music (MusicGen) locally."""

import logging
import subprocess
import tempfile
from pathlib import Path

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "data" / "audio"


def generate_voiceover(text: str, output_name: str = "narration") -> Path | None:
    """Generate speech from text using Piper TTS.

    Requires: piper-tts installed (`pip install piper-tts`)
    and a voice model downloaded.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{output_name}.wav"

    voice_model = settings.piper_voice_model
    if not voice_model:
        log.error("PIPER_VOICE_MODEL not configured")
        return None

    try:
        result = subprocess.run(
            [
                "piper",
                "--model", voice_model,
                "--output_file", str(out_path),
            ],
            input=text,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            log.error("Piper TTS failed: %s", result.stderr)
            return None

        log.info("Voiceover saved: %s", out_path)
        return out_path

    except FileNotFoundError:
        log.error("Piper TTS not installed — run: pip install piper-tts")
        return None
    except subprocess.TimeoutExpired:
        log.error("Piper TTS timed out")
        return None


def generate_music(
    prompt: str = "cinematic background music, ambient, emotional",
    duration_seconds: int = 30,
    output_name: str = "bgmusic",
) -> Path | None:
    """Generate background music using MusicGen via the audiocraft CLI.

    Requires: audiocraft installed (`pip install audiocraft`)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{output_name}.wav"

    try:
        # Use audiocraft's Python API via subprocess
        script = f"""
import torchaudio
from audiocraft.models import MusicGen
from audiocraft.data.audio import audio_write

model = MusicGen.get_pretrained('{settings.musicgen_model}')
model.set_generation_params(duration={duration_seconds})
wav = model.generate(['{prompt}'])
audio_write('{str(out_path.with_suffix(""))}', wav[0].cpu(), model.sample_rate, strategy="loudness")
"""
        result = subprocess.run(
            ["python", "-c", script],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min — music gen is slow
        )

        if result.returncode != 0:
            log.error("MusicGen failed: %s", result.stderr[:500])
            return None

        # audiocraft writes with .wav extension
        if out_path.exists():
            log.info("Background music saved: %s", out_path)
            return out_path

        log.error("MusicGen output file not found")
        return None

    except FileNotFoundError:
        log.error("Python not found or audiocraft not installed")
        return None
    except subprocess.TimeoutExpired:
        log.error("MusicGen timed out")
        return None


def generate_scene_narrations(scenes: list[dict]) -> Path | None:
    """Concatenate all scene narrations into a single voiceover file."""
    full_narration = " ... ".join(
        scene.get("narration", "") for scene in scenes if scene.get("narration")
    )

    if not full_narration.strip():
        log.warning("No narration text found in scenes")
        return None

    return generate_voiceover(full_narration, output_name="full_narration")


def generate_scene_music(scenes: list[dict], style: str = "") -> Path | None:
    """Generate background music matched to the video style and total duration."""
    total_duration = sum(scene.get("duration", 3) for scene in scenes)
    # Add a few seconds for transitions
    total_duration += len(scenes)

    music_prompt = f"background music for a {style} video, cinematic, ambient"
    return generate_music(
        prompt=music_prompt,
        duration_seconds=min(total_duration, 30),
        output_name="scene_music",
    )
