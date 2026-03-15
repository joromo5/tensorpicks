"""Generate video clips from images using AnimateDiff via ComfyUI API."""

import json
import logging
import time
import uuid
from pathlib import Path

import httpx

from tensorpicks.core.config import settings

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "data" / "clips"

# ComfyUI workflow for AnimateDiff img2video
ANIMATEDIFF_WORKFLOW = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "sd_xl_base_1.0.safetensors",
        },
    },
    "2": {
        "class_type": "LoadImage",
        "inputs": {
            "image": "",
        },
    },
    "3": {
        "class_type": "ADE_AnimateDiffLoaderWithContext",
        "inputs": {
            "model": ["1", 0],
            "model_name": "v3_sd15_mm.ckpt",
            "context_options": ["4", 0],
        },
    },
    "4": {
        "class_type": "ADE_StandardStaticContextOptions",
        "inputs": {
            "context_length": 16,
            "context_overlap": 4,
        },
    },
    "5": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["1", 1],
            "text": "",
        },
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["1", 1],
            "text": "blurry, static, frozen, low quality, watermark, text, caption",
        },
    },
    "7": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["3", 0],
            "positive": ["5", 0],
            "negative": ["6", 0],
            "latent_image": ["8", 0],
            "seed": 0,
            "steps": 20,
            "cfg": 7,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 0.6,
        },
    },
    "8": {
        "class_type": "VAEEncode",
        "inputs": {
            "pixels": ["2", 0],
            "vae": ["1", 2],
        },
    },
    "9": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["7", 0],
            "vae": ["1", 2],
        },
    },
    "10": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["9", 0],
            "frame_rate": 8,
            "loop_count": 0,
            "filename_prefix": "tensorpicks_clip",
            "format": "video/h264-mp4",
            "pingpong": False,
        },
    },
}


def generate_clip(
    image_path: str,
    motion_prompt: str,
    duration: int = 3,
    seed: int | None = None,
) -> Path | None:
    """Generate an animated video clip from a source image.

    Args:
        image_path: Path to the source image
        motion_prompt: Description of desired motion/animation
        duration: Clip length in seconds
        seed: Optional seed for reproducibility

    Returns: Path to generated MP4 clip or None on failure
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    comfyui_url = settings.comfyui_url
    if not comfyui_url:
        log.error("COMFYUI_URL not configured")
        return None

    if not image_path or not Path(image_path).exists():
        log.error("Source image not found: %s", image_path)
        return None

    # Upload the source image to ComfyUI
    image_filename = _upload_image(comfyui_url, image_path)
    if not image_filename:
        return None

    # Build workflow
    workflow = json.loads(json.dumps(ANIMATEDIFF_WORKFLOW))
    workflow["2"]["inputs"]["image"] = image_filename
    workflow["5"]["inputs"]["text"] = motion_prompt
    workflow["7"]["inputs"]["seed"] = seed or int(time.time() * 1000) % (2**32)
    workflow["10"]["inputs"]["frame_rate"] = max(8, duration * 4)  # ~4 fps per second of output

    if settings.comfyui_checkpoint:
        workflow["1"]["inputs"]["ckpt_name"] = settings.comfyui_checkpoint

    client_id = str(uuid.uuid4())

    try:
        resp = httpx.post(
            f"{comfyui_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=30,
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]
        log.info("Queued video generation: %s", prompt_id)

        # Poll for completion (video takes longer)
        for _ in range(300):  # 5 min timeout
            time.sleep(1)
            hist_resp = httpx.get(
                f"{comfyui_url}/history/{prompt_id}",
                timeout=10,
            )
            hist_resp.raise_for_status()
            history = hist_resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    gifs = node_output.get("gifs", [])
                    if gifs:
                        vid_info = gifs[0]
                        vid_resp = httpx.get(
                            f"{comfyui_url}/view",
                            params={
                                "filename": vid_info["filename"],
                                "subfolder": vid_info.get("subfolder", ""),
                                "type": vid_info.get("type", "output"),
                            },
                            timeout=60,
                        )
                        vid_resp.raise_for_status()

                        out_path = OUTPUT_DIR / f"{prompt_id}.mp4"
                        out_path.write_bytes(vid_resp.content)
                        log.info("Video clip saved: %s", out_path)
                        return out_path

        log.error("Video generation timed out: %s", prompt_id)
        return None

    except httpx.HTTPError as e:
        log.error("ComfyUI video API error: %s", e)
        return None


def _upload_image(comfyui_url: str, image_path: str) -> str | None:
    """Upload an image to ComfyUI's input directory."""
    try:
        with open(image_path, "rb") as f:
            resp = httpx.post(
                f"{comfyui_url}/upload/image",
                files={"image": (Path(image_path).name, f, "image/png")},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("name")
    except Exception as e:
        log.error("Image upload failed: %s", e)
        return None


def generate_scene_clips(scenes: list[dict]) -> list[dict]:
    """Generate a video clip for each scene. Adds 'clip_path' to each scene dict."""
    for i, scene in enumerate(scenes):
        if not scene.get("image_path"):
            log.warning("Skipping scene %d — no source image", i + 1)
            scene["clip_path"] = None
            continue

        log.info("Generating clip for scene %d/%d", i + 1, len(scenes))
        path = generate_clip(
            image_path=scene["image_path"],
            motion_prompt=scene.get("motion_prompt", "slow zoom in"),
            duration=scene.get("duration", 3),
            seed=42 + i,
        )
        scene["clip_path"] = str(path) if path else None

    return scenes
