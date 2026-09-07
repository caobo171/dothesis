"""Draw the proposed research model from the hypotheses the writer stated.

A quantitative thesis is expected to show its model as a figure — boxes for
the constructs, arrows for the hypotheses. The writer already states the
hypotheses in the methodology chapter; this reads them back, asks the model
for the construct/edge structure (with a regex fallback), renders a PNG with
PIL (no matplotlib/graphviz in this environment) and inserts it under the
"proposed model" heading as a markdown image the docx exporter knows how to
place. Any failure returns the body untouched — a draft without the figure is
still a draft.
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# "**H1:** …", "H1. …", "- H1: …", and the labelled forms "**Giả thuyết H1:**",
# "Hypothesis 1:", "Giả thuyết 1:". The id is normalised to H<n>.
_HYP = re.compile(r'^\s*(?:[-*]|\|)?\s*(?:\*\*|__)?\s*\(?(?:(?:giả thuyết|hypothesis|hipótesis|hypothese)\s*)?'
                  r'(H\s?\d+[a-z]?|\d+[a-z]?)\)?\s*(?:\([+\-±]\))?\s*(?:\*\*|__)?\s*[:.\-–)|]\s*(?:\*\*|__)?\s*(.+?)\s*\|?\s*$', re.I)
_HYP_LABELLED = re.compile(r'(?:giả thuyết|hypothesis|hipótesis|hypothese)\s*(?:H\s?)?\d', re.I)
_MODEL_HEAD = re.compile(r'^#{1,6}\s+.*(mô hình nghiên cứu|mô hình đề xuất|research model|conceptual (?:framework|model)|'
                         r'proposed (?:research )?model|khung nghiên cứu|khung khái niệm|hypothes|giả thuyết)', re.I)
# The verb is mandatory: with it optional, the lazy subject group matched a
# single word ("Sự") and the rest of the construct name was swallowed.
# When no heading names the model, the methods/theory chapter still describes
# it; use that (plus the topic) as the extractor's context and placement.
_APPENDIX_HEAD = re.compile(r'phụ lục|appendix|appendices|anhang', re.I)
_METHOD_HEAD = re.compile(r'^#{1,6}\s+.*(phương pháp nghiên cứu|thiết kế nghiên cứu|methodolog|research design|'
                          r'research framework|theoretical framework|khung lý thuyết|cơ sở lý thuyết|literature review|'
                          r'mô hình|model)', re.I)
_ARROW = re.compile(r'^(.*?)\s+(?:có\s+)?(?:(?:tác động|ảnh hưởng|tác dụng)|'
                    r'(?:positively\s+|negatively\s+|significantly\s+)?(?:influences?|affects?|impacts?|has|have|exerts?))'
                    r'\b.*?\s+(?:đến|tới|lên|on|to)\s+(.+?)(?:[.,;]|$)', re.I)
_FONT_CANDIDATES = [
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/Library/Fonts/Arial Unicode.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
]
CAPTION = {'vi': 'Hình: Mô hình nghiên cứu đề xuất (Nguồn: Tác giả đề xuất)',
           'en': 'Figure: Proposed research model (Source: Author)'}


def _strip_md(s: str) -> str:
    return re.sub(r'[*_`]+', '', s).strip()


def collect_hypotheses(md: str, limit: int = 24) -> list[tuple[str, str]]:
    out, seen = [], set()
    for ln in md.split('\n'):
        m = _HYP.match(ln)
        if not m:
            continue
        raw_id = m.group(1).replace(' ', '').upper()
        # A bare number only counts as a hypothesis when the line is labelled
        # ("Giả thuyết 1:"); otherwise "1. Introduction" would be one.
        if not raw_id.startswith('H') and not _HYP_LABELLED.search(ln):
            continue
        hid = raw_id if raw_id.startswith('H') else f'H{raw_id}'
        if hid in seen:
            continue
        seen.add(hid)
        out.append((hid, _strip_md(m.group(2))[:400]))
        if len(out) >= limit:
            break
    return out


def _heuristic_model(hyps: list[tuple[str, str]]) -> dict | None:
    constructs: dict[str, dict] = {}
    edges = []

    def cid(label: str) -> str:
        label = label.strip(' .:')[:45]
        for k, v in constructs.items():
            if v['label'].lower() == label.lower():
                return k
        k = f'C{len(constructs) + 1}'
        constructs[k] = {'id': k, 'label': label, 'role': 'independent'}
        return k

    for hid, text in hyps:
        m = _ARROW.match(text)
        if not m:
            continue
        src, dst = m.group(1), m.group(2)
        src = re.sub(r'^(?:the|các|sự|những)\s+', '', src, flags=re.I)
        if len(src) < 2 or len(dst) < 2:
            continue
        sign = '-' if re.search(r'tiêu cực|ngược chiều|negativ|giảm', text, re.I) else '+'
        edges.append({'h': hid, 'from': cid(src), 'to': cid(dst), 'sign': sign, 'moderates': None})
    if len(constructs) < 2 or not edges:
        return None
    targets = {e['to'] for e in edges}
    sources = {e['from'] for e in edges}
    for k, c in constructs.items():
        c['role'] = 'mediator' if (k in targets and k in sources) else ('dependent' if k in targets else 'independent')
    return {'constructs': list(constructs.values()), 'edges': edges}


def _parse_model_json(raw: str) -> dict:
    """Parse the extractor's JSON, salvaging a truncated response.

    Ten constructs pretty-printed overran the output cap and the reply ended
    mid-edge; a strict json.loads then threw the whole figure away. Constructs
    and edges are flat objects, so every complete {...} block can still be read
    individually."""
    try:
        return json.loads(raw[raw.index('{'):raw.rindex('}') + 1])
    except Exception:  # noqa: BLE001
        pass
    def objs(section: str) -> list[dict]:
        i = raw.find(f'"{section}"')
        if i < 0:
            return []
        j_end = raw.find('"edges"', i + 1) if section == 'constructs' else len(raw)
        out = []
        for m in re.finditer(r'\{[^{}]*\}', raw[i:j_end if j_end > 0 else len(raw)]):
            try:
                out.append(json.loads(re.sub(r',\s*}', '}', m.group(0))))
            except Exception:  # noqa: BLE001
                continue
        return out
    return {'constructs': objs('constructs'), 'edges': objs('edges')}


def _llm_model(model: Any, hyps: list[tuple[str, str]], context: str) -> dict | None:
    if model is None:
        return None
    try:
        from utils.agent_runner import run_agent
        prompt_path = Path(__file__).resolve().parents[1] / 'prompts' / 'utils' / 'model_figure_extract.md'
        user_input = 'HYPOTHESES:\n' + '\n'.join(f'{h}: {t}' for h, t in hyps) + '\n\nCONTEXT:\n' + context[:2500]
        raw = run_agent(model=model, name='Model Figure - Extract', prompt_path=str(prompt_path),
                        user_input=user_input, verbose=False, skip_validation=True, max_retries=2)
        raw = re.sub(r'^```(?:json)?|```$', '', (raw or '').strip(), flags=re.M).strip()
        data = _parse_model_json(raw)
        ids = {c['id'] for c in data.get('constructs', []) if c.get('id') and c.get('label')}
        edges = [e for e in data.get('edges', []) if e.get('from') in ids and e.get('to') in ids]
        if len(ids) < 2 or not edges:
            return None
        data['edges'] = edges
        return data
    except Exception as e:  # noqa: BLE001
        logger.warning(f'Model figure: LLM extraction failed ({e}); using heuristic')
        return None


def _font(size: int):
    from PIL import ImageFont
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines[:4]


def render_png(model: dict, out: Path) -> Path:
    from PIL import Image, ImageDraw
    cons = {c['id']: c for c in model['constructs']}
    cols = {'independent': [], 'mediator': [], 'dependent': [], 'moderator': [], 'control': []}
    for c in cons.values():
        cols.setdefault(c.get('role', 'independent'), cols['independent']).append(c['id'])
    has_mid = bool(cols['mediator'])
    W, H = 2000, 1150
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)
    f_box, f_lab = _font(30), _font(26)
    bw, bh = 400, 120
    xcol = {'independent': 120, 'mediator': 800, 'dependent': 1480 if has_mid else 1250}
    pos: dict[str, tuple[int, int]] = {}

    def place(ids, x, y0, y1):
        if not ids:
            return
        gap = (y1 - y0) / max(len(ids), 1)
        for i, cid in enumerate(ids):
            pos[cid] = (x, int(y0 + gap * i + gap / 2 - bh / 2))

    place(cols['independent'], xcol['independent'], 200, 900)
    place(cols['mediator'], xcol['mediator'], 200, 900)
    place(cols['dependent'], xcol['dependent'], 200, 900)
    place(cols['moderator'], xcol['mediator'] if has_mid else (xcol['independent'] + xcol['dependent']) // 2, 20, 200)
    place(cols['control'], xcol['independent'], 900, 1120)

    for cid, (x, y) in pos.items():
        role = cons[cid].get('role', '')
        fill = {'dependent': '#E8F1FB', 'mediator': '#F3F0FA', 'moderator': '#FFF6E5', 'control': '#F2F2F2'}.get(role, '#F7F7F7')
        d.rounded_rectangle([x, y, x + bw, y + bh], radius=14, fill=fill, outline='#222222', width=3)
        lines = _wrap(d, cons[cid]['label'], f_box, bw - 30)
        th = sum(d.textbbox((0, 0), ln, font=f_box)[3] for ln in lines) + 6 * (len(lines) - 1)
        yy = y + (bh - th) / 2
        for ln in lines:
            tw = d.textlength(ln, font=f_box)
            d.text((x + (bw - tw) / 2, yy), ln, fill='#111111', font=f_box)
            yy += d.textbbox((0, 0), ln, font=f_box)[3] + 6

    def arrow(p1, p2, color='#222222', width=4):
        d.line([p1, p2], fill=color, width=width)
        import math
        ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0]); L = 22
        a = (p2[0] - L * math.cos(ang - 0.45), p2[1] - L * math.sin(ang - 0.45))
        b = (p2[0] - L * math.cos(ang + 0.45), p2[1] - L * math.sin(ang + 0.45))
        d.polygon([p2, a, b], fill=color)

    for e in model['edges']:
        if e['from'] not in pos or e['to'] not in pos:
            continue
        (x1, y1), (x2, y2) = pos[e['from']], pos[e['to']]
        src_role = cons[e['from']].get('role')
        if src_role == 'moderator' and e.get('moderates'):
            a, b = (e['moderates'].split('->') + [''])[:2]
            if a in pos and b in pos:
                (ax, ay), (bx, by) = pos[a], pos[b]
                mid = ((ax + bw + bx) // 2, (ay + by + bh) // 2)
                arrow((x1 + bw // 2, y1 + bh), mid, color='#B8860B')
                lab = f"{e['h']} ({e['sign']})" if e.get('sign') else e['h']
                d.text((mid[0] + 8, mid[1] - 34), lab, fill='#B8860B', font=f_lab)
                continue
        p1 = (x1 + bw, y1 + bh // 2) if x2 > x1 else (x1, y1 + bh // 2)
        p2 = (x2, y2 + bh // 2) if x2 > x1 else (x2 + bw, y2 + bh // 2)
        arrow(p1, p2)
        lab = f"{e['h']} ({e['sign']})" if e.get('sign') else e['h']
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        tw = d.textlength(lab, font=f_lab)
        d.rectangle([mx - tw / 2 - 6, my - 20, mx + tw / 2 + 6, my + 16], fill='white')
        d.text((mx - tw / 2, my - 18), lab, fill='#111111', font=f_lab)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, 'PNG')
    return out


def add_model_figure(body_md: str, ctx) -> str:
    if '![' in body_md and 'research_model' in body_md:
        return body_md  # already placed (resume path)
    hyps = collect_hypotheses(body_md)
    lines = body_md.split('\n')
    # The hypotheses live under the "proposed model" heading. Take the closest
    # heading ABOVE the first hypothesis when it names the model/hypotheses;
    # a generic "conceptual framework" heading earlier in the literature
    # chapter used to win and the figure ended up two chapters too early.
    first_h = next((i for i, ln in enumerate(lines) if _HYP.match(ln)), None)
    head_idx = None
    if first_h is not None:
        for j in range(first_h - 1, -1, -1):
            if lines[j].startswith('#'):
                head_idx = j if _MODEL_HEAD.match(lines[j]) else None
                if head_idx is None:
                    # walk up one more level only if this was a sub-heading of the model section
                    k = next((q for q in range(j - 1, -1, -1) if lines[q].startswith('#')), None)
                    head_idx = k if (k is not None and _MODEL_HEAD.match(lines[k])) else None
                break
    if head_idx is None:
        head_idx = next((i for i, ln in enumerate(lines)
                         if _MODEL_HEAD.match(ln) and not _APPENDIX_HEAD.search(ln)), None)
    span = 60
    if head_idx is None and not hyps:
        head_idx = next((i for i, ln in enumerate(lines) if _METHOD_HEAD.match(ln)), None)
        span = 90
    context = '\n'.join(lines[head_idx:head_idx + span]) if head_idx is not None else ''
    if not hyps and head_idx is None:
        logger.info('Model figure: no hypotheses, no model or methods section; skipping')
        return body_md
    # Many drafts describe the model in prose without numbered hypotheses. The
    # topic the run was started from names the constructs too, so hand both
    # to the extractor and let it number the relationships.
    topic = getattr(ctx, 'topic', '') or ''
    context = (context + '\n\nTOPIC:\n' + topic[:1500]).strip()
    model = _llm_model(getattr(ctx, 'model', None), hyps, context) or (_heuristic_model(hyps) if hyps else None)
    if model:
        for n, e in enumerate(model['edges'], 1):
            if not e.get('h'):
                e['h'] = f'H{n}'
    if not model:
        logger.info('Model figure: could not derive constructs/edges; skipping')
        return body_md
    folders = getattr(ctx, 'folders', None) or {}
    base = Path(folders.get('drafts') or folders.get('exports') or '.')
    png = render_png(model, base / 'figures' / 'research_model.png')
    lang = (getattr(ctx, 'language', 'en') or 'en').split('-')[0].lower()
    caption = CAPTION.get(lang, CAPTION['en'])
    block = ['', f'![{caption}]({png.resolve()})', '']
    if head_idx is not None:
        j = head_idx + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        # keep an opening paragraph under the heading, then the figure
        if j < len(lines) and not lines[j].startswith('#') and not _HYP.match(lines[j]):
            j += 1
        lines[j:j] = block
    else:
        first = next((i for i, ln in enumerate(lines) if _HYP.match(ln)), len(lines))
        lines[first:first] = block
    logger.info(f'Model figure: {len(model["constructs"])} constructs, {len(model["edges"])} edges -> {png}')
    return '\n'.join(lines)
