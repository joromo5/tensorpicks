"""Break a story prompt into a sequence of scenes for video generation."""

import json
import logging

from tensorpicks.core import llm

log = logging.getLogger(__name__)

PLAN_PROMPT = """You are a short-form video director specializing in fast-paced, attention-grabbing content.
Given a story prompt, break it down into 15-20 scenes for a vertical (9:16) video.
Each scene will be turned into a 1-2 second AI-generated video clip and stitched together.
The pacing must be FAST — think TikTok energy. Every scene change keeps the viewer hooked.

Story prompt:
{prompt}

For each scene provide:
- scene_number: int
- image_prompt: A detailed Stable Diffusion prompt for the visual (include style,
  lighting, camera angle, mood — be very specific). Always include "masterpiece,
  best quality, highly detailed" and the art style.
- motion_prompt: Brief description of what motion/animation should happen
  (camera pan, zoom, character movement, etc.) — keep it dynamic
- narration: ONE short punchy sentence of voiceover narration for this scene
- duration: seconds (1-2, keep it snappy)

IMPORTANT:
- 15-20 scenes minimum — fast cuts, never linger
- Keep a consistent art style across all scenes
- Keep character descriptions consistent (same clothing, hair, features)
- Think cinematically — vary camera angles and shot types aggressively
  (close-up, wide, bird's eye, low angle, dutch angle, over-the-shoulder)
- Every scene should have visual contrast from the previous one
- Build tension and momentum — hook in scene 1, escalate, payoff at the end
- Total video should be 20-40 seconds

Output ONLY valid JSON array. No markdown, no explanation.
Example format:
[
  {{
    "scene_number": 1,
    "image_prompt": "...",
    "motion_prompt": "quick zoom in",
    "narration": "...",
    "duration": 1
  }}
]"""

STYLE_PROMPT = """Based on this story prompt, pick the best visual art style.
Choose ONE from: anime, cartoon, cinematic realistic, pixel art, watercolor, comic book, 3d render.
Output ONLY the style name, nothing else.

Prompt: {prompt}"""


def plan_scenes(prompt: str) -> list[dict] | None:
    """Use the LLM to break a prompt into a scene-by-scene plan.

    Returns list of scene dicts or None on failure.
    """
    # First determine art style
    style = llm.chat(STYLE_PROMPT.format(prompt=prompt)).strip().lower()
    log.info("Selected art style: %s", style)

    # Generate scene plan
    raw = llm.chat(PLAN_PROMPT.format(prompt=prompt))

    # Parse JSON from response
    try:
        # Try to extract JSON array from response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            log.error("No JSON array found in planner response")
            return None
        scenes = json.loads(raw[start:end])
    except json.JSONDecodeError as e:
        log.error("Failed to parse scene plan: %s", e)
        return None

    if not scenes or not isinstance(scenes, list):
        log.error("Scene plan is empty or invalid")
        return None

    # Inject consistent style into all image prompts
    for scene in scenes:
        img_prompt = scene.get("image_prompt", "")
        if style not in img_prompt.lower():
            scene["image_prompt"] = f"{img_prompt}, {style} style"
        scene["style"] = style

    log.info("Planned %d scenes for video", len(scenes))
    return scenes
