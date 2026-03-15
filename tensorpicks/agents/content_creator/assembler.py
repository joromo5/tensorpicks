"""Assemble final video from clips + audio using FFmpeg."""

import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "data" / "output"

# 9:16 vertical (1080x1920 for short-form content)
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920


def assemble_video(
    scenes: list[dict],
    narration_path: Path | None = None,
    music_path: Path | None = None,
    output_name: str = "final",
) -> Path | None:
    """Stitch scene clips together with audio into a final vertical video.

    Args:
        scenes: List of scene dicts with 'clip_path' set
        narration_path: Path to voiceover WAV
        music_path: Path to background music WAV
        output_name: Name for the output file

    Returns: Path to final MP4 or None on failure
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{output_name}.mp4"

    # Collect valid clips
    clips = []
    for scene in scenes:
        clip_path = scene.get("clip_path")
        if clip_path and Path(clip_path).exists():
            clips.append(clip_path)

    if not clips:
        log.error("No valid clips to assemble")
        return None

    try:
        # Step 1: Create a concat file for FFmpeg
        concat_file = Path(tempfile.mktemp(suffix=".txt"))
        with open(concat_file, "w") as f:
            for clip in clips:
                f.write(f"file '{clip}'\n")

        # Step 2: Concatenate clips and scale to 9:16
        merged_video = Path(tempfile.mktemp(suffix=".mp4"))
        _run_ffmpeg([
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-vf", f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-r", "24",
            "-pix_fmt", "yuv420p",
            "-an",  # no audio yet
            str(merged_video),
        ])

        if not merged_video.exists():
            log.error("Video concatenation failed")
            return None

        # Step 3: Mix audio tracks if available
        if narration_path or music_path:
            final = _mix_audio(merged_video, narration_path, music_path, out_path)
        else:
            # No audio — just copy
            merged_video.rename(out_path)
            final = out_path

        # Cleanup temp files
        concat_file.unlink(missing_ok=True)
        merged_video.unlink(missing_ok=True)

        if final and final.exists():
            log.info("Final video assembled: %s", final)
            return final

        log.error("Final video assembly failed")
        return None

    except Exception as e:
        log.error("Video assembly error: %s", e)
        return None


def _mix_audio(
    video_path: Path,
    narration_path: Path | None,
    music_path: Path | None,
    out_path: Path,
) -> Path | None:
    """Mix narration and music, then mux with video."""
    try:
        inputs = ["-i", str(video_path)]
        filter_parts = []
        audio_inputs = 0

        if narration_path and narration_path.exists():
            inputs.extend(["-i", str(narration_path)])
            audio_inputs += 1

        if music_path and music_path.exists():
            inputs.extend(["-i", str(music_path)])
            audio_inputs += 1

        if audio_inputs == 0:
            # No audio — just copy video
            _run_ffmpeg(inputs + ["-c", "copy", str(out_path)])
            return out_path

        if audio_inputs == 2:
            # Mix narration (louder) + music (quieter)
            _run_ffmpeg(inputs + [
                "-filter_complex",
                "[1:a]volume=1.0[narr];[2:a]volume=0.3[music];"
                "[narr][music]amix=inputs=2:duration=longest[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(out_path),
            ])
        else:
            # Single audio track
            vol = "1.0" if narration_path else "0.5"
            _run_ffmpeg(inputs + [
                "-filter_complex", f"[1:a]volume={vol}[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(out_path),
            ])

        return out_path if out_path.exists() else None

    except Exception as e:
        log.error("Audio mixing error: %s", e)
        return None


def _run_ffmpeg(args: list[str]):
    """Run an FFmpeg command."""
    cmd = ["ffmpeg", "-y"] + args
    log.info("Running: %s", " ".join(cmd[:6]) + "...")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        log.error("FFmpeg failed: %s", result.stderr[-500:] if result.stderr else "unknown error")
