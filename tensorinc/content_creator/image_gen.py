"""Generate images using Stable Diffusion via ComfyUI API."""

import io
import json
import logging
import time
import uuid
from pathlib import Path

import httpx

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "data" / "images"

# Basic ComfyUI workflow for SDXL text-to-image (9:16 vertical)
WORKFLOW_TEMPLATE = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 7,
            "denoise": 1,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "euler",
            "scheduler": "normal",
            "seed": 0,
            "steps": 25,
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "sd_xl_base_1.0.safetensors",
        },
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "batch_size": 1,
            "height": 1280,
            "width": 720,
        },
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": "",
        },
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": "blurry, low quality, distorted, deformed, ugly, watermark, text, caption, subtitle",
        },
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2],
        },
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "tensorinc",
            "images": ["8", 0],
        },
    },
}


def generate_image(prompt: str, seed: int | None = None) -> Path | None:
    """Generate a single image from a text prompt via ComfyUI.

    Args:
        prompt: Stable Diffusion prompt text
        seed: Optional seed for reproducibility

    Returns: Path to saved image or None on failure
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    comfyui_url = settings.comfyui_url
    if not comfyui_url:
        log.error("COMFYUI_URL not configured")
        return None

    # Build workflow
    workflow = json.loads(json.dumps(WORKFLOW_TEMPLATE))
    workflow["6"]["inputs"]["text"] = prompt
    workflow["3"]["inputs"]["seed"] = seed or int(time.time() * 1000) % (2**32)

    # Use configured checkpoint if set
    if settings.comfyui_checkpoint:
        workflow["4"]["inputs"]["ckpt_name"] = settings.comfyui_checkpoint

    client_id = str(uuid.uuid4())

    try:
        # Queue the prompt
        resp = httpx.post(
            f"{comfyui_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=30,
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]
        log.info("Queued image generation: %s", prompt_id)

        # Poll for completion
        for _ in range(120):  # 2 min timeout
            time.sleep(1)
            hist_resp = httpx.get(
                f"{comfyui_url}/history/{prompt_id}",
                timeout=10,
            )
            hist_resp.raise_for_status()
            history = hist_resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                # Find the SaveImage node output
                for node_id, node_output in outputs.items():
                    images = node_output.get("images", [])
                    if images:
                        img_info = images[0]
                        # Download the image
                        img_resp = httpx.get(
                            f"{comfyui_url}/view",
                            params={
                                "filename": img_info["filename"],
                                "subfolder": img_info.get("subfolder", ""),
                                "type": img_info.get("type", "output"),
                            },
                            timeout=30,
                        )
                        img_resp.raise_for_status()

                        out_path = OUTPUT_DIR / f"{prompt_id}.png"
                        out_path.write_bytes(img_resp.content)
                        log.info("Image saved: %s", out_path)
                        return out_path

        log.error("Image generation timed out for prompt_id: %s", prompt_id)
        return None

    except httpx.HTTPError as e:
        log.error("ComfyUI API error: %s", e)
        return None


def generate_scene_images(scenes: list[dict]) -> list[dict]:
    """Generate an image for each scene. Adds 'image_path' to each scene dict."""
    for i, scene in enumerate(scenes):
        log.info("Generating image for scene %d/%d", i + 1, len(scenes))
        path = generate_image(
            prompt=scene["image_prompt"],
            seed=42 + i,  # deterministic seeds for consistency
        )
        scene["image_path"] = str(path) if path else None
    return scenes
