"""Capability-driven multimodal user-message construction.

The chat surface lets users attach files (PDF, CSV, images, plain text) to a
message. Two independent questions decide the shape of the outgoing message,
and conflating them was design-doc defect 1:

  1. WHICH WIRE FORMAT — the provider of the active brain, derived from the
     ModelSpec (route+model) via detect_provider(spec), never env-sniffed.
  2. CAN THE BRAIN SEE — `supports_vision`. A text-only brain (Ofox +
     qwen-plus) gets every attachment flattened to TEXT: images through the
     Gemini vision sidecar, PDFs through extraction. Vision is a runtime
     capability, not a property of the wire format.

Per-provider block shapes once the brain can see:

  - Gemini: `{type: "media", mime_type, data | file_uri}` blocks alongside
    text blocks in a list-shaped HumanMessage.content. Files <20MB ride
    inline (base64); larger ones go through the Gemini File API and
    reference a URI.
  - OpenAI-compatible: `{type: "image_url", image_url}` data-URI blocks for
    images; no first-class document type exists, so non-images are extracted
    to text (see _textualize).
  - Anthropic: native `image` / `document` base64 blocks (≤32MB inline).

The dispatcher keeps the agent runtime provider-agnostic — it calls
`build_user_message(text, attachments, provider, supports_vision=...)` and
gets back a `HumanMessage` it can drop into the LangGraph payload.

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
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    # Type-only: the runtime import stays lazy inside detect_provider so
    # import-light callers don't pay for model_factory at module load.
    from agent.model_factory import ModelSpec


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
            # Extension-less pasted screenshots (guess is None) get a magic-byte
            # sniff so vision still recognizes them as images.
            mime_type = guess or _sniff_image_mime(data) or "application/octet-stream"
        return cls(filename=p.name, bytes=data, mime_type=mime_type)


def build_user_message(
    text: str,
    attachments: list[Attachment],
    provider: Provider,
    *,
    supports_vision: bool | None = None,
) -> HumanMessage:
    """Compose a HumanMessage carrying both prose and attached files —
    capability-driven, not provider-driven (spec §2).

    With no attachments this returns a plain text-content message — same
    shape the rest of the pipeline used before multimodal landed, so the
    happy path is unchanged.

    `supports_vision=None` keeps each provider's historical default (gemini/
    anthropic can see; openai fail-closed cannot) so the one existing caller
    that omits it (agent/tools/output_parse.py:128, provider="gemini")
    behaves identically. Callers that know the active ModelSpec pass
    spec.supports_vision explicitly (agent/runtime.py does).
    """
    if not attachments:
        return HumanMessage(content=text)

    if supports_vision is None:
        supports_vision = provider in ("gemini", "anthropic")

    if not supports_vision:
        # Text-only brain: EVERYTHING becomes text — images via the vision
        # sidecar, PDFs via extraction (vision fallback for scans). Vision is
        # a runtime capability, not a model property.
        return _build_text_only_message(text, attachments)
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


# ---- Text-only brains (capability path) -----------------------------

# Below this many characters a "PDF extraction" is treated as a scan: pdfminer
# has no OCR, so an image-only PDF yields near-empty text and the agent would
# silently get nothing (spec Risk 3). The vision sidecar reads scans instead.
_MIN_PDF_TEXT_CHARS = 200


def _transcribe_via_vision(att: Attachment) -> str:
    """Turn an image / scanned-PDF attachment into text with the vision model.

    Isolated as the single function tests stub — same pattern as
    output_parse._vision_read — so the network/model boundary stays out of
    the test suite. Anti-fabrication: the prompt forbids invented values.
    """
    from agent.model_factory import make_vision_model  # noqa: PLC0415 — lazy, heavy dep

    prompt = (
        "Transcribe the full content of this file faithfully as plain "
        "text/Markdown. Render tables as Markdown tables. Do NOT invent or "
        "guess values; mark anything unreadable as [unreadable]."
    )
    # The vision model is always Gemini (see make_vision_model), so the
    # message uses the Gemini block shape regardless of the text brain.
    msg = _build_gemini_message(prompt, [att])
    out = make_vision_model().invoke([msg])
    return _flatten_content(getattr(out, "content", ""))


def _textualize(att: Attachment) -> tuple[str, str]:
    """(label, body) for one attachment as plain text — the text-only-brain
    path of the capability table (spec §2). Never raises: the worst input
    degrades to a lossy decode, not a dead turn."""
    name = (att.filename or "").lower()
    if att.mime_type.startswith("image/"):
        return ("image transcription", _transcribe_via_vision(att))
    if att.mime_type == "application/pdf" or name.endswith(".pdf"):
        from agent.pdf_extract import extract_pdf_text  # noqa: PLC0415 — agent-layer, lazy
        body, _pages = extract_pdf_text(att.bytes)
        if len((body or "").strip()) < _MIN_PDF_TEXT_CHARS:
            # Scanned PDF: extraction came back hollow → vision fallback
            # rather than proceeding with an empty message (Risk 3).
            return ("scanned-PDF transcription", _transcribe_via_vision(att))
        return ("PDF text", body)
    return ("file content", att.bytes.decode("utf-8", errors="replace"))


def _build_text_only_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    parts = [text]
    for att in attachments:
        label, body = _textualize(att)
        parts.append(f"\n\n[ATTACHMENT {att.filename} — {label}]\n{body}")
    return HumanMessage(content="".join(parts))


# ---- OpenAI-compatible ----------------------------------------------

def _build_openai_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    """Vision-capable OpenAI-compatible brain: images ride as data-URI
    image_url blocks; everything else becomes text (OpenAI-compat chat has no
    first-class document type, and extraction is lossless enough for result
    tables). The old NotImplementedError landmine is gone — a failing raise
    on a normal upload is a worse outcome than a text fallback."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for att in attachments:
        if att.mime_type.startswith("image/"):
            data_url = f"data:{att.mime_type};base64,{base64.b64encode(att.bytes).decode('ascii')}"
            blocks.append({"type": "image_url", "image_url": {"url": data_url}})
        else:
            label, body = _textualize(att)
            blocks.append({"type": "text",
                           "text": f"\n\n[ATTACHMENT {att.filename} — {label}]\n{body}"})
    return HumanMessage(content=blocks)


# ---- Anthropic ------------------------------------------------------

def _build_anthropic_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    """Anthropic native blocks: images as `image`, PDFs as `document` (base64,
    ≤32MB inline per their docs — no File API hop needed), the rest as text.
    Implemented now (was a NotImplementedError stub) because the capability
    table says a vision-capable brain gets native blocks (spec §2)."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for att in attachments:
        b64 = base64.b64encode(att.bytes).decode("ascii")
        if att.mime_type.startswith("image/"):
            blocks.append({"type": "image",
                           "source": {"type": "base64", "media_type": att.mime_type, "data": b64}})
        elif att.mime_type == "application/pdf":
            blocks.append({"type": "document",
                           "source": {"type": "base64", "media_type": "application/pdf", "data": b64}})
        else:
            label, body = _textualize(att)
            blocks.append({"type": "text",
                           "text": f"\n\n[ATTACHMENT {att.filename} — {label}]\n{body}"})
    return HumanMessage(content=blocks)


def detect_provider(spec: ModelSpec | None = None) -> Provider:
    """Provider of the ACTIVE brain, derived from the ModelSpec (route+model).

    The old body sniffed env (ANTHROPIC_API_KEY else "gemini") and ignored
    DOTHESIS_MODEL_ROUTE entirely — on route=ofox + qwen-plus it emitted
    Gemini-native {type:"media"} blocks into an OpenAI-compatible endpoint, a
    malformed request that broke EVERY attachment (design-doc defect 1).
    Deriving from the spec also collapses the third "what model am I on"
    source of truth into agent.model_factory.
    """
    from agent.model_factory import spec_from_env  # noqa: PLC0415 — lazy; keeps import-light callers cheap

    spec = spec or spec_from_env()
    if spec.route in ("ofox", "openrouter", "openai"):
        # OpenAI-compatible wire format on both gateways AND on OpenAI direct —
        # `openai` must be listed or a direct-route brain falls through to the
        # native branch below and gets Gemini-native {type:"media"} blocks, the
        # exact malformed-request defect this function was written to fix.
        return "openai"
    # native route mirrors model_factory._native's branch condition exactly.
    if os.getenv("ANTHROPIC_API_KEY") and "claude" in spec.model:
        return "anthropic"
    return "gemini"


@dataclass(frozen=True, slots=True)
class VisionResolution:
    """How to read an image for the ACTIVE model: which provider block-format to
    build, and whether to send it to the Gemini vision *sidecar* (a separate
    Gemini/VL model) rather than the text brain."""
    provider: Provider
    use_sidecar: bool


def resolve_vision(spec: ModelSpec | None = None) -> VisionResolution:
    """Pick the image block-format + client for the active model (spec §3.2).

    Reuses detect_provider (route→provider) and spec.supports_vision — nothing
    re-derived. When the brain can see images (native Claude, or a vision-capable
    OpenAI-compatible model) we send them to the brain; otherwise we fall back to
    the Gemini vision sidecar with Gemini-native blocks. DOTHESIS_VISION_FORCE_SIDECAR=1
    forces the sidecar path (deploy-time rollback for an unverified gateway)."""
    from agent.model_factory import spec_from_env  # noqa: PLC0415 — lazy
    spec = spec or spec_from_env()
    if os.getenv("DOTHESIS_VISION_FORCE_SIDECAR") == "1":
        return VisionResolution("gemini", True)
    provider = detect_provider(spec)
    if provider == "anthropic":
        return VisionResolution("anthropic", False)  # brain sees images
    if provider == "openai":
        if spec.supports_vision:
            return VisionResolution("openai", False)  # brain over OpenAI-compat
        return VisionResolution("gemini", True)       # text-only brain → sidecar
    return VisionResolution("gemini", True)           # native Gemini → sidecar


_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)


def _sniff_image_mime(data: bytes) -> str | None:
    """Best-effort image MIME from magic bytes — for extension-less pasted
    screenshots where mimetypes.guess_type() returns nothing."""
    for magic, mime in _IMAGE_MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _flatten_content(content: Any) -> str:
    """LLM message content → str. Gemini 3.x returns a list of parts."""
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content or "")
