"""Content Creator Agent — generates short-form video from Slack prompts."""

import logging
import time
from pathlib import Path

from tensorpicks.core.agent import Agent
from tensorpicks.core import slack
from tensorpicks.core.config import settings
from tensorpicks.agents.content_creator.listener import job_queue, start_listener, stop_listener
from tensorpicks.agents.content_creator.planner import plan_scenes
from tensorpicks.agents.content_creator.image_gen import generate_scene_images
from tensorpicks.agents.content_creator.video_gen import generate_scene_clips
from tensorpicks.agents.content_creator.audio_gen import generate_scene_narrations, generate_scene_music
from tensorpicks.agents.content_creator.assembler import assemble_video

log = logging.getLogger(__name__)

PROGRESS_MSG = "🎬 *Content Creator — {status}*\n\n{detail}"

COMPLETE_MSG = """🎬 *Content Creator — Video Ready!*

*Prompt:* {prompt}
*Scenes:* {scene_count}
*Duration:* ~{duration}s
*Style:* {style}

Video file: `{output_path}`"""

ERROR_MSG = """❌ *Content Creator — Failed*

*Prompt:* {prompt}
*Error:* {error}

Check the logs for details."""


class ContentCreatorAgent(Agent):
    name = "content_creator"

    def run(self) -> None:
        """Process all pending jobs from the Slack listener queue."""
        self.log.info("Checking for content creation jobs...")

        # Process all queued jobs
        jobs_processed = 0
        while not job_queue.empty():
            try:
                job = job_queue.get_nowait()
            except Exception:
                break

            self._process_job(job)
            jobs_processed += 1

        if jobs_processed == 0:
            self.log.info("No content jobs in queue")
        else:
            self.log.info("Processed %d content creation jobs", jobs_processed)

    def run_listener(self) -> None:
        """Start the Slack listener and process jobs as they come in.

        This is a long-running mode — call this instead of run() to
        have the agent listen continuously.
        """
        self.log.info("Starting content creator in listener mode...")
        start_listener()

        try:
            while True:
                try:
                    job = job_queue.get(timeout=5)
                    self._process_job(job)
                except Exception:
                    continue
        except KeyboardInterrupt:
            self.log.info("Shutting down content creator listener")
            stop_listener()

    def _process_job(self, job: dict):
        """Process a single content creation job end-to-end."""
        prompt = job["prompt"]
        channel = job.get("channel") or settings.slack_channel

        self.log.info("Processing content job: %s", prompt[:80])

        # 1. Plan scenes
        self._update_progress(channel, "Planning scenes...", f"Prompt: _{prompt}_")
        scenes = plan_scenes(prompt)
        if not scenes:
            self._post_error(channel, prompt, "Failed to plan scenes from prompt")
            return

        style = scenes[0].get("style", "cinematic")
        self.log.info("Planned %d scenes in %s style", len(scenes), style)

        # 2. Generate images
        self._update_progress(
            channel,
            f"Generating {len(scenes)} images...",
            f"Style: {style} | This takes a few minutes per image",
        )
        scenes = generate_scene_images(scenes)
        failed_images = sum(1 for s in scenes if not s.get("image_path"))
        if failed_images == len(scenes):
            self._post_error(channel, prompt, "All image generations failed")
            return

        # 3. Animate images into video clips
        self._update_progress(
            channel,
            f"Animating {len(scenes) - failed_images} clips...",
            "Using AnimateDiff — this is the slow part",
        )
        scenes = generate_scene_clips(scenes)
        failed_clips = sum(1 for s in scenes if not s.get("clip_path"))
        if failed_clips == len(scenes):
            self._post_error(channel, prompt, "All video clip generations failed")
            return

        # 4. Generate audio
        self._update_progress(channel, "Generating voiceover + music...", "Almost done")
        narration_path = generate_scene_narrations(scenes)
        music_path = generate_scene_music(scenes, style=style)

        # 5. Assemble final video
        self._update_progress(channel, "Assembling final video...", "Stitching clips + audio")
        timestamp = int(time.time())
        final_path = assemble_video(
            scenes=scenes,
            narration_path=narration_path,
            music_path=music_path,
            output_name=f"video_{timestamp}",
        )

        if not final_path:
            self._post_error(channel, prompt, "Final video assembly failed")
            return

        # 6. Post result
        total_duration = sum(s.get("duration", 3) for s in scenes)
        slack.post(
            COMPLETE_MSG.format(
                prompt=prompt,
                scene_count=len(scenes),
                duration=total_duration,
                style=style,
                output_path=final_path,
            ),
            channel=channel,
        )

        # Upload the video file to Slack
        self._upload_video(channel, final_path, prompt)

        self.log.info("Content creation complete: %s", final_path)

    def _upload_video(self, channel: str, video_path: Path, prompt: str):
        """Upload the final video to Slack."""
        try:
            from slack_sdk import WebClient
            client = WebClient(token=settings.slack_bot_token)
            client.files_upload_v2(
                channel=channel,
                file=str(video_path),
                title=f"Generated video: {prompt[:50]}",
                initial_comment="Here's your video!",
            )
        except Exception as e:
            self.log.error("Failed to upload video to Slack: %s", e)
            slack.post(
                f"⚠️ Video was generated but upload failed. "
                f"File is at: `{video_path}`",
                channel=channel,
            )

    def _update_progress(self, channel: str, status: str, detail: str):
        slack.post(PROGRESS_MSG.format(status=status, detail=detail), channel=channel)

    def _post_error(self, channel: str, prompt: str, error: str):
        self.log.error("Content creation failed: %s", error)
        slack.post(ERROR_MSG.format(prompt=prompt, error=error), channel=channel)
