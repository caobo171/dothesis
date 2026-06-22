"""M3 instrument tool — turn a drafted questionnaire into a Google Form.

Google Forms can only be CREATED via OAuth (forms.body) or a service account —
there is no API-key path. To give students a real form with zero setup and no
credentials, this tool emits a ready-to-run **Google Apps Script**: the student
pastes it into script.google.com and clicks Run, and the form is created in
*their own* Google account (they own it). A fully-automated service-account
path can be layered on later without changing this tool's contract.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool


def _js(v) -> str:
    """Render a Python value as a safe JS literal (json is valid JS for these)."""
    return json.dumps(v, ensure_ascii=False)


@tool
def make_google_form_script(title: str, questions: list[dict], description: str = "") -> str:
    """Generate a Google Apps Script that builds a Google Form for a questionnaire.

    Use this in M3 once the instrument's questions are drafted. The student runs
    the returned script once (script.google.com → paste → Run) and gets a real
    Google Form in their own Google Drive — no credentials needed. Present the
    script to the user in a code block with the instructions.

    Args:
        title: Form title.
        questions: list of question dicts. Each:
            {"text": str,
             "type": "short"|"paragraph"|"multiple_choice"|"checkbox"|"dropdown"|"scale",
             "options": [str]          # for multiple_choice/checkbox/dropdown
             "required": bool,
             "scale_min": int, "scale_max": int,
             "scale_min_label": str, "scale_max_label": str}   # for scale
        description: optional form description / instructions for respondents.
    """
    out: list[str] = ["function createForm() {",
                      f"  var form = FormApp.create({_js(title or 'Survey')});"]
    if description:
        out.append(f"  form.setDescription({_js(description)});")
    out.append("  var item;")

    for q in (questions or []):
        text = str(q.get("text") or q.get("title") or "")
        qtype = str(q.get("type") or "short").lower()
        opts = [str(o) for o in (q.get("options") or [])]
        required = bool(q.get("required", False))

        if qtype in ("multiple_choice", "mc", "radio"):
            out.append(f"  item = form.addMultipleChoiceItem().setTitle({_js(text)}).setChoiceValues({_js(opts)});")
        elif qtype in ("checkbox", "checkboxes"):
            out.append(f"  item = form.addCheckboxItem().setTitle({_js(text)}).setChoiceValues({_js(opts)});")
        elif qtype in ("dropdown", "list"):
            out.append(f"  item = form.addListItem().setTitle({_js(text)}).setChoiceValues({_js(opts)});")
        elif qtype in ("paragraph", "long"):
            out.append(f"  item = form.addParagraphTextItem().setTitle({_js(text)});")
        elif qtype in ("scale", "likert"):
            lo, hi = int(q.get("scale_min", 1)), int(q.get("scale_max", 5))
            line = f"  item = form.addScaleItem().setTitle({_js(text)}).setBounds({lo}, {hi})"
            if q.get("scale_min_label") or q.get("scale_max_label"):
                line += f".setLabels({_js(str(q.get('scale_min_label', '')))}, {_js(str(q.get('scale_max_label', '')))})"
            out.append(line + ";")
        else:  # short text (default)
            out.append(f"  item = form.addTextItem().setTitle({_js(text)});")
        out.append(f"  item.setRequired({_js(required)});")

    out.append("  Logger.log('EDIT URL (to edit): ' + form.getEditUrl());")
    out.append("  Logger.log('SHARE URL (send to respondents): ' + form.getPublishedUrl());")
    out.append("}")
    script = "\n".join(out)

    instructions = (
        "Create this Google Form in YOUR Google account (no setup needed):\n"
        "1. Open https://script.google.com and click New project.\n"
        "2. Delete the placeholder code, paste the script below, click Run (▶).\n"
        "3. Approve the one-time permission prompt.\n"
        "4. Open View → Execution log: copy the EDIT URL (to tweak the form) and "
        "the SHARE URL (to send to respondents)."
    )
    return json.dumps({"instructions": instructions, "apps_script": script}, ensure_ascii=False)
