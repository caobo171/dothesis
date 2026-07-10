"""
ABOUTME: Shared Gemini client wrapper for new google.genai API.
ABOUTME: Provides backward-compatible interface matching legacy GenerativeModel-style usage.
"""

import logging
import os
from typing import Any, Optional, Protocol, runtime_checkable

try:
    from google import genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)


@runtime_checkable
class GenerativeModel(Protocol):
    """Protocol for objects that can generate content (duck typing)."""

    def generate_content(
        self, prompt: Any, generation_config: Any = None, safety_settings: Any = None
    ) -> Any:
        """Generate content from a prompt."""
        ...


class GenerationConfig:
    """
    Configuration for content generation.

    Replaces genai.GenerationConfig from old API.
    """

    def __init__(
        self,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        response_mime_type: Optional[str] = None,
    ):
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.response_mime_type = response_mime_type


# Fallback chain when the chosen Gemini model is overloaded (503 / UNAVAILABLE).
# Each entry is a list of models to try in order if the previous one fails.
# Pro/preview models are flaky during peak hours; flash variants are far more reliable.
_FALLBACK_CHAINS = {
    "gemini-3-pro-preview":   ["gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    # gemini-3.5-flash is the default model; degrade to the 2.5 flash variants
    # when it's overloaded so a 503 doesn't kill a turn with no downgrade path.
    "gemini-3.5-flash":       ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "gemini-3-flash-preview": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "gemini-2.5-pro":         ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "gemini-2.5-flash":       ["gemini-2.5-flash-lite"],
    "gemini-2.5-flash-lite":  [],
    "gemini-2.0-flash-exp":   ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "gemini-1.5-pro":         ["gemini-1.5-flash"],
    "gemini-1.5-flash":       [],
}


def _is_overload_error(err: Exception) -> bool:
    """Detect Gemini overload / temporary-unavailable signals."""
    s = str(err).lower()
    cls = err.__class__.__name__.lower()
    return (
        " 503" in f" {s}" or
        "503:" in s or
        "unavailable" in s or
        "overloaded" in s or
        "high demand" in s or
        "resource exhausted" in s or
        "timed out" in s or
        "readtimeout" in cls or
        "deadline exceeded" in s
    )


class GeminiModelWrapper:
    """
    Compatibility wrapper for the new google.genai API.

    Mimics legacy GenerativeModel interface so existing code continues to work
    unchanged. Adds an automatic-fallback chain: if the configured model returns
    503 / overloaded / timeout, the wrapper switches to the next model in the
    chain and retries. The switch is permanent for the lifetime of this wrapper
    so subsequent calls go straight to the new model.
    """

    def __init__(
        self,
        client: "genai.Client",
        model_name: str,
        temperature: float = 0.7,
    ):
        """
        Initialize wrapper.

        Args:
            client: google.genai.Client instance
            model_name: Model name (e.g., "gemini-2.0-flash")
            temperature: Default temperature for generation
        """
        self.client = client
        self.model_name = model_name
        self.default_temperature = temperature
        # Build the in-order list of models we'll try if the current one overloads.
        self._fallback_queue = list(_FALLBACK_CHAINS.get(model_name, []))

    def generate_content(
        self,
        prompt: Any,
        generation_config: Any = None,
        safety_settings: Any = None,
    ) -> Any:
        """
        Generate content using the new API.

        Compatible with old GenerativeModel.generate_content() signature.
        Automatically falls back to a lighter model if the current one is overloaded.

        Args:
            prompt: Text prompt or list of prompts
            generation_config: GenerationConfig or dict with settings
            safety_settings: Ignored (new API handles safety differently)

        Returns:
            Response object with .text attribute
        """
        _ = safety_settings
        config = {"temperature": self.default_temperature}

        if generation_config:
            if hasattr(generation_config, "temperature"):
                config["temperature"] = generation_config.temperature
            if hasattr(generation_config, "max_output_tokens"):
                config["max_output_tokens"] = generation_config.max_output_tokens
            if hasattr(generation_config, "response_mime_type") and generation_config.response_mime_type:
                config["response_mime_type"] = generation_config.response_mime_type
            if isinstance(generation_config, dict):
                config.update(generation_config)

        if isinstance(prompt, str):
            contents = prompt
        elif isinstance(prompt, list):
            contents = "\n".join(str(p) for p in prompt)
        else:
            contents = str(prompt)

        # Try the current model; on overload, walk the fallback chain.
        attempt_model = self.model_name
        last_err: Optional[Exception] = None
        while True:
            try:
                return self.client.models.generate_content(
                    model=attempt_model,
                    contents=contents,
                    config=config if config else None,
                )
            except Exception as err:
                last_err = err
                if not _is_overload_error(err) or not self._fallback_queue:
                    raise
                next_model = self._fallback_queue.pop(0)
                logger.warning(
                    "Gemini model %s overloaded (%s) — switching to %s for the rest of this run",
                    attempt_model, err.__class__.__name__, next_model,
                )
                # Persist the switch so subsequent calls go directly to the new model.
                self.model_name = next_model
                attempt_model = next_model
                # Loop will retry once with the new model.
        # Unreachable, but keep mypy happy.
        if last_err:
            raise last_err

    def count_tokens(self, text: str) -> Any:
        """Count tokens in text."""
        return self.client.models.count_tokens(
            model=self.model_name,
            contents=text,
        )


def create_gemini_client(
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.0-flash",
    temperature: float = 0.7,
) -> GeminiModelWrapper:
    """
    Create a Gemini client wrapper.

    Convenience function that handles API key from environment.

    Args:
        api_key: API key (defaults to GEMINI_API_KEY or GOOGLE_API_KEY env var)
        model_name: Model name
        temperature: Default temperature

    Returns:
        GeminiModelWrapper instance

    Raises:
        ImportError: If google-genai not installed
        ValueError: If no API key found
    """
    if not genai:
        raise ImportError(
            "google-genai not installed. Run: pip install google-genai>=1.0.0"
        )

    # Route the native-genai path through Ofox's Gemini-native endpoint when the
    # deployment is on Ofox (google-genai SDK is Ofox-compatible; the key rides in
    # x-goog-api-key). Ofox needs provider-prefixed ids (google/gemini-2.5-flash),
    # so add the prefix if the caller passed a bare gemini id. This keeps the
    # citation planner / vision paths on Ofox instead of requiring a Google key.
    route = (os.getenv("ORCHESTRATOR_LLM_ROUTE") or os.getenv("DOTHESIS_MODEL_ROUTE") or "").lower()
    ofox_key = os.getenv("OFOX_API_KEY")
    if route == "ofox" and ofox_key:
        from google.genai.types import HttpOptions  # noqa: PLC0415
        m = model_name if "/" in model_name else f"google/{model_name}"
        client = genai.Client(api_key=ofox_key,
                              http_options=HttpOptions(base_url="https://api.ofox.ai/gemini"))
        return GeminiModelWrapper(client, m, temperature)

    api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "API key required. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
        )

    client = genai.Client(api_key=api_key)
    return GeminiModelWrapper(client, model_name, temperature)
