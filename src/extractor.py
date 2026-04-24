"""LLM-backed metadata extraction using OpenAI structured outputs."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from openai import APIError, OpenAI
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class Paper(BaseModel):
    """Structured metadata returned by the model."""

    title: str = Field(description="Paper title, or 'Unknown' if illegible.")
    author: str = Field(description="Corresponding/first author full name, or 'Unknown'.")


class MetadataExtractor:
    """Thin wrapper around the OpenAI chat completions structured-output API."""

    def __init__(self, api_key: str, model: str, prompt: str, *, timeout: float = 60.0, max_retries: int = 2) -> None:
        self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)
        self._model = model
        self._prompt = prompt

    def extract(self, image_path: Path) -> Paper:
        data_url = f"data:image/png;base64,{self._encode(image_path)}"
        try:
            response = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self._prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                response_format=Paper,
            )
        except APIError:
            log.exception("OpenAI API call failed for %s", image_path)
            raise

        parsed = response.choices[0].message.parsed
        if parsed is None:
            refusal = response.choices[0].message.refusal
            raise RuntimeError(f"Model refused or returned no structured output: {refusal!r}")
        return parsed

    @staticmethod
    def _encode(image_path: Path) -> str:
        return base64.b64encode(image_path.read_bytes()).decode("ascii")
