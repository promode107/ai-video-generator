"""
image_client.py
Wraps calls to the Azure OpenAI image generation deployment (gpt-image-1-mini).
"""

import os
import base64
from openai import AzureOpenAI


def get_image_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_IMAGE_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_IMAGE_KEY"],
        api_version=os.environ["IMAGE_API_VERSION"],
    )


def generate_scene_image(prompt: str, size: str = "1536x1024") -> bytes:
    """
    Generates a single still image for a scene's visual description.
    This still frame becomes the input to the Ken Burns animation step
    (see video_composer.py) so the final output is not a static image.
    """
    client = get_image_client()
    deployment = os.environ["IMAGE_DEPLOYMENT_NAME"]

    # Add a consistent style directive so all scenes in one video look cohesive
    styled_prompt = (
        f"{prompt}. Style: clean flat medical-education illustration, "
        f"soft color palette, no text overlays, no watermarks."
    )

    result = client.images.generate(
        model=deployment,
        prompt=styled_prompt,
        size=size,
        n=1,
    )
    b64_data = result.data[0].b64_json
    return base64.b64decode(b64_data)