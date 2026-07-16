"""Re-export shim — the implementation moved to agent/pdf_extract.py.

Moved because the capability-driven multimodal path (agent/multimodal.py)
needs extract_pdf_text, and agent/ importing api.app.* is the recurring
agent->app layering defect this repo bans (headless convergence spec §2).
The shim keeps routers/uploads.py and other api-layer imports untouched.
"""
from agent.pdf_extract import extract_pdf_text  # noqa: F401
