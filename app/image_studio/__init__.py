"""Stable Diffusion backed human image studio for AutoSellerAI.

The package intentionally keeps the UI-facing character choices separate from the
AUTOMATIC1111 payload.  This makes it possible to evolve prompt engineering,
checkpoint-specific settings and extension support without teaching operators the
WebUI prompt syntax.
"""

from app.image_studio.schemas import HumanImageRequest
from app.image_studio.service import create_generation, list_generations

__all__ = ["HumanImageRequest", "create_generation", "list_generations"]
