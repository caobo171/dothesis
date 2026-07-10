"""Provider-aware multimodal user-message construction.

The chat surface lets users attach files (PDF, CSV, plain text) to a
message. The backend has to hand those files to whichever LLM provider
the agent runs on. Each provider has its own content-block shape:

  - Gemini: `{type: "media", mime_type, data | file_uri}` blocks alongside
    text blocks in a list-shaped HumanMessage.content. Files <20MB ride
    inline (base64); larger ones go through the Gemini File API and
    reference a URI.
  - OpenAI (stub): `{type: "image_url", image_url}` for vision-capable
    models; for documents OpenAI doesn't yet have a first-class file
    type, so this module raises NotImplementedError until we decide on
    a fallback (extract-then-text vs. responses API documents).

The dispatcher keeps the agent runtime provider-agnostic — it calls
`build_user_message(text, attachments, provider)` and gets back a
`HumanMessage` it can drop into the LangGraph payload.

The 20MB inline-vs-File-API threshold matches Gemini's documented
request-size cap. Beyond that limit Gemini rejects the inline payload
with a 400; we proactively switch to the File API so the user doesn't
see the failure.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import HumanMessage


logger = logging.getLogger(__name__)


Provider = Literal["gemini", "openai", "anthropic"]


# Gemini's documented inline-data ceiling. Above this we MUST upload via
# the File API and reference a URI. Anthropic accepts up to 32MB inline
# per their docs; the smaller Gemini number is the binding constraint
# while we only support one provider.
INLINE_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


@dataclass(slots=True)
class Attachment:
    """One file the user attached to a message.

    `bytes` is the raw file content. `mime_type` defaults to a guess from
    the filename suffix when the caller doesn't know. `display_name` is
    the short label the LLM might cite (logs / error messages).
    """
    filename: str
    bytes: bytes
    mime_type: str
    display_name: str | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.bytes)

    @classmethod
    def from_path(cls, path: Path | str, *, mime_type: str | None = None) -> "Attachment":
        """Load an attachment from disk. Used by chat_v3 to materialize an
        upload_id → bytes from the workspace mirror."""
        p = Path(path)
        data = p.read_bytes()
        if mime_type is None:
            guess, _ = mimetypes.guess_type(p.name)
            mime_type = guess or "application/octet-stream"
        return cls(filename=p.name, bytes=data, mime_type=mime_type)


def build_user_message(
    text: str,
    attachments: list[Attachment],
    provider: Provider,
) -> HumanMessage:
    """Compose a HumanMessage carrying both prose and attached files.

    With no attachments this returns a plain text-content message — same
    shape the rest of the pipeline used before multimodal landed, so the
    happy path is unchanged.
    """
    if not attachments:
        return HumanMessage(content=text)

    if provider == "gemini":
        return _build_gemini_message(text, attachments)
    if provider == "openai":
        return _build_openai_message(text, attachments)
    if provider == "anthropic":
        return _build_anthropic_message(text, attachments)
    raise ValueError(f"unknown provider {provider!r}")


# ---- Gemini ---------------------------------------------------------

def _build_gemini_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    """Build a Gemini-shaped HumanMessage.

    Each file rides as a `{"type": "media", ...}` block alongside the
    text block. Small files inline as base64; larger ones get uploaded
    via the google-genai File API and referenced by URI.
    """
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for att in attachments:
        if att.size_bytes <= INLINE_MAX_BYTES:
            blocks.append({
                "type": "media",
                "mime_type": att.mime_type,
                "data": base64.b64encode(att.bytes).decode("ascii"),
            })
            logger.info(
                "gemini multimodal: inlined %s (%d bytes, %s)",
                att.filename, att.size_bytes, att.mime_type,
            )
        else:
            file_uri = _upload_to_gemini_files(att)
            blocks.append({
                "type": "media",
                "mime_type": att.mime_type,
                "file_uri": file_uri,
            })
            logger.info(
                "gemini multimodal: File API URI for %s (%d bytes, %s) → %s",
                att.filename, att.size_bytes, att.mime_type, file_uri,
            )
    return HumanMessage(content=blocks)


def _upload_to_gemini_files(att: Attachment) -> str:
    """Upload a large attachment via the Gemini File API and return its URI.

    The google-genai SDK does the multi-part heavy lifting; we just hand
    it the bytes and the mime type. The returned `uri` is what LC's
    Gemini chat client expects in a `file_uri` content block.
    """
    # Lazy import — the SDK is heavy and we only need it for big files.
    from google import genai as _genai

    # Route through Ofox's Gemini-native endpoint when the deployment is on Ofox,
    # else native Google. NOTE: the Gemini Files API (large-attachment upload) is a
    # Gemini feature; qwen (the text brain) can't do vision, so image/large-file
    # understanding needs a Gemini/VL model regardless of the text-model choice.
    route = (os.getenv("DOTHESIS_MODEL_ROUTE") or "").lower()
    ofox_key = os.getenv("OFOX_API_KEY")
    if route == "ofox" and ofox_key:
        from google.genai.types import HttpOptions  # noqa: PLC0415
        client = _genai.Client(api_key=ofox_key,
                               http_options=HttpOptions(base_url="https://api.ofox.ai/gemini"))
    else:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY / GEMINI_API_KEY (or OFOX_API_KEY on route=ofox) required "
                "to upload >20MB attachments via the Gemini File API"
            )
        client = _genai.Client(api_key=api_key)
    # Files API takes an `io.BytesIO` or a `Path`; the in-memory route
    # avoids a temp-file dance and lines up with how we get bytes from
    # the workspace mirror.
    import io as _io
    uploaded = client.files.upload(
        file=_io.BytesIO(att.bytes),
        config={"mime_type": att.mime_type, "display_name": att.display_name or att.filename},
    )
    # `.uri` is the canonical reference; `.name` is the resource id.
    return uploaded.uri  # type: ignore[no-any-return]


# ---- OpenAI (stub — future) -----------------------------------------

def _build_openai_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    """Placeholder for the eventual OpenAI multimodal path.

    OpenAI's Chat Completions handles images via `image_url` content
    blocks but doesn't have a first-class document type yet. The likely
    landing is the Assistants API + file IDs, or extracting text in
    Python and shipping it as plain prose. Until we pick a strategy,
    refusing here is honest — the user gets a clear error instead of a
    "file silently ignored" surprise.
    """
    # Images can be carried inline as data-URI image_url even today.
    image_blocks: list[dict[str, Any]] = []
    other: list[Attachment] = []
    for att in attachments:
        if att.mime_type.startswith("image/"):
            data_url = f"data:{att.mime_type};base64,{base64.b64encode(att.bytes).decode('ascii')}"
            image_blocks.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        else:
            other.append(att)
    if other:
        names = ", ".join(a.filename for a in other)
        raise NotImplementedError(
            f"OpenAI provider doesn't yet support non-image attachments "
            f"({names}). Switch the agent model to a Gemini variant or "
            f"land the OpenAI document path first."
        )
    return HumanMessage(content=[{"type": "text", "text": text}, *image_blocks])


# ---- Anthropic (stub — future) --------------------------------------

def _build_anthropic_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    """Anthropic uses a `{type:'document', source:{type:'base64', media_type, data}}`
    block shape for PDFs (Claude 3.5+). This is feasible without an
    intermediate File API call — Anthropic accepts up to 32MB inline.
    Kept as a placeholder until the agent runtime actually routes a
    Claude run; the wiring is mechanical."""
    raise NotImplementedError(
        "Anthropic multimodal path not yet wired — see TODO in agent/multimodal.py"
    )


def detect_provider() -> Provider:
    """Best-effort guess of which provider the agent is currently using.

    Mirrors agent/runtime.py:_default_model() precedence: Claude when
    ANTHROPIC_API_KEY is set, else Gemini. OpenAI is reserved for the
    future explicit switch.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "gemini"
