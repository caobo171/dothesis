"""The shared blog illustration library: one picture per scene, paid for once.

Ported from WELE's `generate.blog.images.ts` (commit 4ce4e699), which measured
the thing worth knowing: 489 image slots across their corpus resolved to 64
distinct scenes, so generating per article costs about twenty-five times what
generating per scene does. The same holds here and harder — every DoThesis post
belongs to one of seven categories and one of ten archetypes, so the whole bank
needs about three dozen pictures no matter how many posts it grows to.

So `docs/blog-image-library.json` holds one prompt per scene and, once it has
been generated, one url. A seed points at a scene with
`"source": "library:<key>"`, an empty key is generated on first use and written
back, and no key is ever billed twice.

Three things differ from WELE and each one follows from our situation.

**The library is hosted out of the repo**, at `web/public/img/blog/<key>.webp`,
referenced as `/img/blog/<key>.webp`. DoThesis has no public image host: the S3
client only mints 300-second presigned urls, and there is no CDN in front of
anything the public may read. Committing the files instead works because the
library is ~35 files rather than one per post, so the repo cost is bounded and
does not grow with the corpus; because Next serves and optimises `public/`
directly, so it needs no bucket, no distribution and no `next.config`
`remotePatterns` entry; and because version control is what makes "paid for
once" actually true — a lost file means paying for it again. Not
`web/public/blog/...`: that path collides with the `/blog/[locale]/[slug]`
route.

**`image_url` is stored root-relative**, `/img/blog/x.webp`. An absolute origin
in the database bakes the environment into the row; the two places that need an
absolute url (JSON-LD and the OG metadata) put it through `absoluteUrl()` in
`web/app/blog/_lib/site.ts`, which passes an `http(s)` url through untouched.

**One hero per post, no in-body figures.** These are reference articles whose
informative visual is a table (see `structure.md`), so a second illustration
would be decoration competing with the thing the reader came for.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from . import repo_root

# --------------------------------------------------------------------------
# Where things live
# --------------------------------------------------------------------------

#: Next serves `web/public/img/blog/x.webp` at `/img/blog/x.webp`.
PUBLIC_URL_PREFIX = "/img/blog"


def library_path() -> Path:
    return Path(repo_root()) / "docs" / "blog-image-library.json"


def public_dir() -> Path:
    return Path(repo_root()) / "web" / "public" / "img" / "blog"


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

GEMINI_MODEL = "gemini-2.5-flash-image"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent")
OPENAI_MODEL = "gpt-image-2"
OPENAI_ENDPOINT = "https://api.openai.com/v1/images/generations"
OPENAI_SIZE = "1536x1024"

#: Quality tier for gpt-image-2. Medium at 1536x1024 is the default because the
#: library made the per-image price stop mattering: 37 scenes cover 900+ posts,
#: so the whole library costs about as much as one bad afternoon of per-post
#: generation, and the picture is looked at by every reader of every article in
#: its archetype. Override with --quality or BLOG_IMAGE_QUALITY.
OPENAI_QUALITY_DEFAULT = "medium"
OPENAI_QUALITIES = ("low", "medium", "high")

#: Estimates, printed in the report and nothing else. Nothing here bills by
#: itself and the invoice is the authority. The gpt-image-2 medium figure is
#: taken from WELE's measurement that medium at 1536x1024 prices close to
#: Gemini's flat rate (their generate.blog.images.ts, commit 77f325d6).
IMAGE_COST_USD = {
    ("openai", "low"): 0.012,
    ("openai", "medium"): 0.042,
    ("openai", "high"): 0.167,
    ("gemini", "medium"): 0.039,
}

#: 1200px is the widest the blog measure can use (the article column is 720px
#: and the listing card is 1200x630), so anything larger is bytes the reader
#: pays for and never sees.
MAX_WIDTH = 1200
WEBP_QUALITY = 82
TIMEOUT_S = 180

#: 3:2 out of the generator, cropped by CSS where a card wants 1200x630.
ASPECT_RATIO = "3:2"


class ImageError(RuntimeError):
    """A generation or conversion that could not produce an image."""


def _http_post(url: str, *, headers: dict[str, str], payload: dict) -> dict:
    """POST JSON, return JSON. Raises `ImageError` on anything but a 2xx.

    `httpx` is imported here rather than at module scope for the reason in this
    package's `__init__`: `qa.py` is reached from a skill shim running under a
    bare `python3`, and its import walks the package.
    """
    import httpx  # noqa: PLC0415

    try:
        res = httpx.post(url, headers=headers, json=payload, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:  # DNS blip, read timeout, reset connection
        raise ImageError(f"image request failed: {type(e).__name__}") from e
    if res.status_code >= 300:
        # The url carries the api key as a query parameter, so the url never
        # goes into a message. The body is truncated for the same reason.
        raise ImageError(f"image request failed: HTTP {res.status_code} "
                         f"{res.text[:300]}")
    return res.json()


def _generate_gemini(prompt: str) -> bytes:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ImageError("GEMINI_API_KEY is not set")
    model = os.getenv("GEMINI_IMAGE_MODEL") or GEMINI_MODEL
    body = _http_post(
        f"{GEMINI_ENDPOINT.format(model=model)}?key={api_key}",
        headers={"Content-Type": "application/json"},
        payload={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": ASPECT_RATIO},
            },
        },
    )
    candidates = body.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    for part in parts:
        data = (part.get("inlineData") or {}).get("data")
        if data:
            return base64.b64decode(data)
    reason = candidates[0].get("finishReason") if candidates else "no candidates"
    raise ImageError(f"gemini returned no image data ({reason})")


def _generate_openai(prompt: str) -> bytes:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ImageError("OPENAI_API_KEY is not set")
    body = _http_post(
        OPENAI_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload={"model": OPENAI_MODEL, "prompt": prompt, "n": 1,
                 "size": OPENAI_SIZE, "quality": openai_quality()},
    )
    data = body.get("data") or []
    b64 = data[0].get("b64_json") if data else None
    if not b64:
        raise ImageError("openai response carried no image data")
    return base64.b64decode(b64)


def openai_quality() -> str:
    """`low` | `medium` | `high`, from BLOG_IMAGE_QUALITY, defaulting to medium."""
    value = (os.getenv("BLOG_IMAGE_QUALITY") or "").strip().lower()
    return value if value in OPENAI_QUALITIES else OPENAI_QUALITY_DEFAULT


def provider(*, use_gemini: bool = False) -> str:
    """Which generator this run uses.

    gpt-image-2 by default. WELE picked the cheaper generator per image because
    they were paying per article; the library changed the arithmetic. Thirty-seven
    scenes serve nine hundred posts, so the difference between the two providers
    across the whole library is under two dollars, while the difference in the
    picture is on every page of an archetype forever. Quality decides, and
    gpt-image-2 at medium is the better hero.

    `--gemini` forces the other one, and it is also the fallback when there is
    no OpenAI key.
    """
    if use_gemini or not os.getenv("OPENAI_API_KEY"):
        return "gemini"
    return "openai"


def estimated_cost(count: int, *, use_gemini: bool = False) -> float:
    name = provider(use_gemini=use_gemini)
    tier = openai_quality() if name == "openai" else "medium"
    return count * IMAGE_COST_USD.get((name, tier), 0.042)


def generate(prompt: str, *, use_gemini: bool = False) -> bytes:
    """Raw image bytes from the configured generator."""
    if provider(use_gemini=use_gemini) == "gemini":
        return _generate_gemini(prompt)
    return _generate_openai(prompt)


def to_webp(raw: bytes) -> tuple[bytes, int, int]:
    """(webp bytes, width, height), capped at `MAX_WIDTH` and never upscaled."""
    from PIL import Image  # noqa: PLC0415 — Pillow off the shim's import path

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as e:  # noqa: BLE001 — Pillow raises a zoo of these
        raise ImageError(f"could not decode the generated image ({e})") from e
    img = img.convert("RGB")
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buf.getvalue(), img.width, img.height


# --------------------------------------------------------------------------
# The library file
# --------------------------------------------------------------------------


def load_library(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    path = Path(path) if path else library_path()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_library(library: dict[str, dict[str, Any]], path: str | Path | None = None) -> None:
    """Write the library back, preserving key order and the diacritics.

    Callers must re-read immediately before writing. Several posts in one run
    want the same key, and a copy held across a generate would write back a
    snapshot missing whatever a sibling resolved in the meantime — that is
    WELE's recorded lesson, not a hypothetical.
    """
    path = Path(path) if path else library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------

#: The ten archetypes each have `<archetype>-1..6`; a slug whose archetype has
#: no variants falls back to its category key.
#:
#: Three was not enough, and the category hub is where it showed. A hub lists
#: thirty posts of two or three archetypes, so with three variants the best a
#: page could do was three distinct pictures and seven rows came out with four.
#: Six is the number where a hub page stops repeating within a screen; the
#: second three were generated on 2026-09-09 for $1.26 at gpt-image-2 medium.
VARIANTS_PER_ARCHETYPE = 6

#: Vietnamese alt text, one line per library key, describing the scene the
#: prompt asks for. It lives here rather than in the JSON so the library keeps
#: WELE's `{prompt, url}` shape, and it is written by hand because alt text is
#: for a reader with a screen reader, not for a crawler.
ALT_VI: dict[str, str] = {
    # Categories
    "spss": "Sinh viên ngồi trước máy tính trong phòng máy của trường, bên cạnh là tập kết quả in ra",
    "thong-ke": "Bàn làm việc nhìn từ trên xuống với sổ tay mở, máy tính bỏ túi và một tách trà",
    "khao-sat": "Sinh viên đưa bảng hỏi kẹp trên clipboard cho một bạn học trong sân trường",
    "nghien-cuu-khoa-hoc": "Nhóm sinh viên trình bày đề tài trước vài giảng viên trong phòng hội thảo",
    "khoa-luan-tot-nghiep": "Sinh viên ôm quyển khóa luận đóng bìa đi dọc hành lang trường",
    "smartpls": "Sinh viên ngồi trước màn hình lớn, cạnh bàn phím là bản vẽ tay các vòng tròn nối bằng mũi tên",
    "mo-hinh-nghien-cuu": "Giảng viên vẽ các ô nối bằng mũi tên lên bảng trắng, một sinh viên ngồi xem",
    # term-la-gi
    "term-la-gi-1": "Sinh viên ngồi sát màn hình laptop buổi tối, một tay đặt trên trang giấy in bên cạnh",
    "term-la-gi-2": "Trang kết quả in ra đặt trên bàn gỗ nhìn từ trên xuống, có bút chì và bút dạ quang",
    "term-la-gi-3": "Sinh viên ngồi trên bậc thềm thư viện với quyển vở mở trên đầu gối, đang suy nghĩ",
    # spss-howto
    "spss-howto-1": "Sinh viên ngồi ở bàn rộng với laptop mở và tập output in ra xếp gọn bên cạnh",
    "spss-howto-2": "Hai sinh viên chung một laptop ở bàn căng tin, một bạn chỉ vào màn hình",
    "spss-howto-3": "Bàn làm việc nhìn từ trên xuống với laptop, chuột rời, một tách nước và tập giấy in",
    # smartpls-howto
    "smartpls-howto-1": "Sinh viên ngồi trước màn hình lớn, vẽ các vòng tròn và mũi tên ra tờ giấy bên cạnh",
    "smartpls-howto-2": "Hai sinh viên ở bàn thư viện cùng nhìn một sơ đồ in khổ lớn, một bạn lần theo đường mũi tên",
    "smartpls-howto-3": "Góc bàn học ban đêm với laptop dưới đèn bàn và sơ đồ vẽ tay dán trên tường",
    # test
    "test-1": "Sinh viên cầm hai trang in đặt cạnh nhau để đối chiếu",
    "test-2": "Giảng viên hướng dẫn và sinh viên ngồi đối diện, cùng nhìn một trang in đặt giữa bàn",
    "test-3": "Bàn nhìn từ trên xuống với hai chồng giấy, một máy tính bỏ túi và cây bút đặt ở giữa",
    # model-theory
    "model-theory-1": "Giảng đường nhìn từ hàng ghế cuối, giảng viên đứng nhỏ phía trên bục",
    "model-theory-2": "Sinh viên ở bàn thư viện với ba quyển sách mở, đang chép lại một sơ đồ vào vở",
    "model-theory-3": "Bức tường ghim đầy thẻ giấy nối bằng dây, một sinh viên đứng lùi lại quan sát",
    # scale
    "scale-1": "Cận cảnh hai bàn tay cầm clipboard, cây bút đang đánh dấu vào một ô trên phiếu",
    "scale-2": "Sinh viên xếp các mẩu giấy cắt rời thành từng nhóm trên mặt bàn",
    "scale-3": "Sinh viên với tay lên kệ thư viện rút một quyển luận văn đóng bìa",
    # thesis-writing
    "thesis-writing-1": "Sinh viên viết tay vào sổ bên cạnh chiếc laptop đã gập, ánh sáng buổi sáng qua cửa sổ",
    "thesis-writing-2": "Giảng viên hướng dẫn và sinh viên ngồi đối diện với chồng bản in các chương ở giữa",
    "thesis-writing-3": "Máy in đang nhả từng trang ra bàn làm việc yên tĩnh",
    # survey
    "survey-1": "Sinh viên đưa điện thoại cho một bạn học xem ở hành lang",
    "survey-2": "Bốn sinh viên ngồi quanh bàn điền phiếu khảo sát giấy",
    "survey-3": "Chồng phiếu khảo sát đã điền đặt cạnh laptop, một bàn tay vỗ cho chồng giấy thẳng cạnh",
    # topic-list
    "topic-list-1": "Sinh viên và giảng viên hướng dẫn trao đổi trước một danh sách viết tay đặt giữa bàn",
    "topic-list-2": "Bảng ghim đầy mẩu giấy trong phòng tự học, một sinh viên đứng khoanh tay nhìn",
    "topic-list-3": "Sinh viên rút một quyển đóng bìa ra khỏi hàng dài trên kệ thư viện",
    # troubleshoot
    "troubleshoot-1": "Sinh viên ngả người ra khỏi laptop lúc khuya, một tay đưa lên trán, chỉ có đèn bàn sáng",
    "troubleshoot-2": "Hai sinh viên ở một bàn, một bạn cúi qua vai bạn kia nhìn và chỉ vào màn hình",
    "troubleshoot-3": "Bàn làm việc lúc khuya nhìn từ trên xuống: laptop, tách cà phê nguội và hai tờ giấy vo nhàu",
    # term-la-gi, the second three (2026-09-09)
    "term-la-gi-4": "Sinh viên ngồi cạnh cửa sổ trên tàu, sách giáo trình mở trên đùi",
    "term-la-gi-5": "Cận cảnh bàn tay lật một trang trong quyển sách tra cứu dày đặt trên bàn",
    "term-la-gi-6": "Sinh viên đứng đọc thông báo dán trên bảng tin của khoa, túi đeo một bên vai",
    # spss-howto, the second three (2026-09-09)
    "spss-howto-4": "Laptop mở trên bàn bếp buổi sáng sớm, bát và thìa đẩy sang một bên",
    "spss-howto-5": "Sinh viên ngồi bàn làm việc với màn hình phụ dựng dọc, trang giấy in kẹp trên giá bên cạnh",
    "spss-howto-6": "Cận cảnh hai bàn tay đặt trên bàn phím, quyển sổ lò xo mở dựng phía sau",
    # smartpls-howto, the second three (2026-09-09)
    "smartpls-howto-4": "Sinh viên đứng làm việc với laptop kê trên chồng sách, đang vẽ vào tập giấy nhỏ",
    "smartpls-howto-5": "Cận cảnh bàn tay vẽ các vòng tròn nối nhau lên giấy kẻ ô bằng bút mảnh",
    "smartpls-howto-6": "Hai sinh viên trước bảng trắng, một bạn vẽ chuỗi ô, bạn kia cầm trang giấy in",
    # test, the second three (2026-09-09)
    "test-4": "Sinh viên trải bốn trang giấy in thành hàng trên bàn, hai tay đặt lên hai trang ngoài cùng",
    "test-5": "Cận cảnh bút dạ quang kẻ dọc theo một cột trên trang giấy in",
    "test-6": "Sinh viên đứng chờ bên máy photocopy trong hành lang khoa, kẹp tài liệu dưới cánh tay",
    # model-theory, the second three (2026-09-09)
    "model-theory-4": "Sinh viên ngồi nghiêng trong phòng seminar, ghi chép vào sổ trong khi những người khác lắng nghe",
    "model-theory-5": "Chồng bài báo khoa học dán tab màu ở mép, đặt trên bàn thư viện, một bàn tay đặt lên trên cùng",
    "model-theory-6": "Sinh viên trải tờ giấy khổ lớn ra bàn và vẽ chuỗi các ô nối nhau",
    # scale, the second three (2026-09-09)
    "scale-4": "Sinh viên đánh số vào bảng hỏi in ra bằng bút, cây thước đặt dọc theo lề",
    "scale-5": "Cận cảnh bàn tay cho tờ bảng hỏi vào phong bì trên mặt bàn",
    "scale-6": "Hai sinh viên đối chiếu hai bảng hỏi in, mỗi người cầm một tờ giơ lên",
    # thesis-writing, the second three (2026-09-09)
    "thesis-writing-4": "Sinh viên ngồi trong ô bàn thư viện ban đêm, chỉ một ngọn đèn sáng giữa dãy bàn tối",
    "thesis-writing-5": "Cận cảnh bút đỏ ghi chú vào lề một chương in ra",
    "thesis-writing-6": "Sinh viên ôm chồng chương đóng quyển đi xuống cầu thang ngoài trời trong trường",
    # survey, the second three (2026-09-09)
    "survey-4": "Sinh viên ngồi bàn gấp nhỏ ngoài giảng đường với tờ đăng ký và lọ bút",
    "survey-5": "Cận cảnh điện thoại cầm trên tay hiện biểu mẫu trống, bên cạnh là danh sách giấy trên bàn",
    "survey-6": "Sinh viên phân loại các bảng hỏi đã điền thành ba chồng trên mặt bàn rộng",
    # topic-list, the second three (2026-09-09)
    "topic-list-4": "Sinh viên ngồi bàn quán cà phê với quyển sổ chép tay, đang gạch bỏ một dòng",
    "topic-list-5": "Cận cảnh bàn tay ghim một tờ giấy nhỏ vào bảng nút chi chít giấy",
    "topic-list-6": "Hai sinh viên vừa đi trên lối đi trong trường vừa trò chuyện, một bạn cầm tờ giấy gấp",
    # troubleshoot, the second three (2026-09-09)
    "troubleshoot-4": "Sinh viên đứng bên cửa sổ, laptop đã gập kẹp dưới cánh tay, dừng lại một lúc",
    "troubleshoot-5": "Cận cảnh bàn tay bấm một phím trên laptop, trang giấy in nằm hờ dưới máy",
    "troubleshoot-6": "Sinh viên và trợ giảng ngồi cùng bàn trong phòng máy, cả hai nhìn vào một màn hình",
}


def _stable_hash(text: str) -> int:
    """A hash that survives the process.

    Not `hash()`: `PYTHONHASHSEED` randomises it per interpreter, so the same
    slug would land on a different variant on every run and half the corpus
    would churn its picture for nothing.
    """
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16)


def variants_for(archetype: str | None, library: dict[str, Any]) -> list[str]:
    if not archetype:
        return []
    keys = [f"{archetype}-{i}" for i in range(1, VARIANTS_PER_ARCHETYPE + 1)]
    return [k for k in keys if k in library]


def library_key(slug: str, archetype: str | None, category: str | None,
                library: dict[str, Any], *, previous: str | None = None) -> str | None:
    """The library key for one seed, or None when nothing in the library fits.

    `<archetype>-<1..3>` picked by a stable hash of the slug, so the choice is
    the same on every run and the three variants come out roughly even. An
    archetype with no variants falls back to the category key.

    `previous` is the key the seed immediately above got in backlog priority
    order. Two neighbours showing one picture is the failure the rotation in
    WELE's `assign_library.py` exists to prevent, so a collision steps to the
    next variant — deterministic, because the order it walks is the file order.
    """
    variants = variants_for(archetype, library)
    if not variants:
        return category if category in library else None
    index = _stable_hash(slug) % len(variants)
    key = variants[index]
    if previous is not None and key == previous and len(variants) > 1:
        key = variants[(index + 1) % len(variants)]
    return key


@dataclass
class Stats:
    """What one run did, for the cost line at the end."""

    generated: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    would_generate: list[str] = field(default_factory=list)
    assigned: int = 0
    bytes_written: int = 0


def seed_files(seed_dir: str | Path) -> list[Path]:
    """Every seed file, in backlog priority order.

    The `NNNN-` filename prefix IS the priority, which is what makes "two
    adjacent seeds must differ" a well-defined statement.
    """
    seed_dir = Path(seed_dir)
    posts = seed_dir / "posts"
    base = posts if posts.is_dir() else seed_dir
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob("*.json") if p.name != "categories.json")


def assign(seed_dir: str | Path, *, lib_path: str | Path | None = None,
           dry_run: bool = False, stats: Stats | None = None) -> dict[Path, str]:
    """Give every seed a hero pointing at a library key. Returns {path: key}.

    The seed gets `images: [{"id": "hero", "source": "library:<key>", "alt":
    ...}]`, and `image_url` too once that key has been generated. A seed whose
    key is not in the library keeps whatever it had and is reported.
    """
    stats = stats if stats is not None else Stats()
    library = load_library(lib_path)
    chosen: dict[Path, str] = {}
    previous: str | None = None

    for path in seed_files(seed_dir):
        try:
            seed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"  skip {path.name}: {e}")
            continue
        # The translated edition hashes the slug it was translated FROM, so one
        # article carries one picture in both languages. Hashing its own slug
        # gave `what-is-cfa` a different scene from `cfa-la-gi`, which reads as
        # two articles to anyone who follows the language switch.
        slug = seed.get("source_slug") or seed.get("slug") or path.stem
        key = library_key(slug, seed.get("archetype"), seed.get("category"),
                          library, previous=previous)
        if key is None:
            print(f"  no library key for {slug} "
                  f"(archetype {seed.get('archetype')!r}, category {seed.get('category')!r})")
            stats.missing.append(slug)
            continue

        seed["images"] = [{
            "id": "hero",
            "source": f"library:{key}",
            "alt": ALT_VI.get(key, ""),
        }]
        url = (library.get(key) or {}).get("url")
        if url:
            seed["image_url"] = url
        chosen[path] = key
        previous = key
        stats.assigned += 1
        if not dry_run:
            _write_seed(path, seed)

    return chosen


def _write_seed(path: Path, seed: dict) -> None:
    path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hero_keys(seed_dir: str | Path) -> dict[Path, str]:
    """{path: key} read back from seeds that already carry `library:` heroes."""
    out: dict[Path, str] = {}
    for path in seed_files(seed_dir):
        try:
            seed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for img in seed.get("images") or []:
            source = img.get("source") or ""
            if source.startswith("library:"):
                out[path] = source[len("library:"):].strip()
                break
    return out


def sync_image_urls(chosen: dict[Path, str], library: dict[str, Any]) -> int:
    """Copy a key's url onto every seed pointing at it. Returns rows changed."""
    changed = 0
    for path, key in chosen.items():
        url = (library.get(key) or {}).get("url")
        if not url:
            continue
        try:
            seed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if seed.get("image_url") == url:
            continue
        seed["image_url"] = url
        _write_seed(path, seed)
        changed += 1
    return changed


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def resolve(key: str, *, lib_path: str | Path | None = None,
            out_dir: str | Path | None = None,
            generator: Callable[[str], bytes] | None = None,
            force: bool = False, dry_run: bool = False,
            use_gemini: bool = False, stats: Stats | None = None) -> str | None:
    """The url for one library key, generating it once if it has none.

    This is the whole feature. A key with a url is handed back without touching
    a generator; an empty key is generated, converted, written to
    `web/public/img/blog/` and written back into the library file, so the next
    post that wants the same scene costs nothing.
    """
    stats = stats if stats is not None else Stats()
    lib_path = Path(lib_path) if lib_path else library_path()
    out_dir = Path(out_dir) if out_dir else public_dir()

    library = load_library(lib_path)
    entry = library.get(key)
    if entry is None:
        # Reported, not raised: an assignment can name a key nobody has written
        # a prompt for yet, and losing the other thirty-six pictures to one
        # typo is a much worse outcome than a line of output.
        print(f"  library has no key {key!r} (see {lib_path})")
        stats.missing.append(key)
        return None

    # `force` regenerates — but only once per run. Two seeds asking for the same
    # key under --force must still bill once, which is the entire point.
    already = key in stats.generated
    if entry.get("url") and (already or not force):
        stats.reused.append(key)
        return entry["url"]

    if dry_run:
        stats.would_generate.append(key)
        print(f"  would generate {key}")
        return None

    raw = (generator or (lambda p: generate(p, use_gemini=use_gemini)))(entry["prompt"])
    data, width, height = to_webp(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{key}.webp").write_bytes(data)
    url = f"{PUBLIC_URL_PREFIX}/{key}.webp"

    # Re-read before writing back. See `save_library`.
    fresh = load_library(lib_path)
    fresh.setdefault(key, dict(entry))["url"] = url
    save_library(fresh, lib_path)

    stats.generated.append(key)
    stats.bytes_written += len(data)
    print(f"  generated {key} -> {url}  {width}x{height}, {len(data) / 1024:.0f} KB")
    return url


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def cost_lines(stats: Stats, *, posts: int, library_size: int,
               use_gemini: bool = False) -> list[str]:
    """The comparison this feature exists to win. Always printed.

    Per-scene against per-post is the whole argument for a library, and a
    number nobody prints is a number nobody checks. The unit price is an
    estimate; the invoice is the authority.
    """
    name = provider(use_gemini=use_gemini)
    tier = openai_quality() if name == "openai" else "medium"
    unit = IMAGE_COST_USD.get((name, tier), 0.042)
    spent = len(stats.generated) * unit
    whole_library = library_size * unit
    per_post = posts * unit
    lines = [
        f"  generated {len(stats.generated)}, reused {len(stats.reused)}, "
        f"missing {len(stats.missing)}"
        + (f", would generate {len(stats.would_generate)}" if stats.would_generate else ""),
        f"  provider        {name} {tier} (about ${unit:.3f} an image)",
        f"  spent this run  ${spent:.2f}",
        f"  whole library   ${whole_library:.2f}  ({library_size} scenes, once, ever)",
    ]
    if posts:
        ratio = (per_post / whole_library) if whole_library else 0
        lines.append(
            f"  per-post would  ${per_post:.2f}  ({posts} posts)"
            + (f", {ratio:.0f}x the library" if ratio else ""))
    return lines


def run(*, seed_dir: str | Path | None = None, do_assign: bool = False,
        do_generate: bool = False, force: bool = False, use_gemini: bool = False,
        dry_run: bool = False, lib_path: str | Path | None = None,
        out_dir: str | Path | None = None,
        generator: Callable[[str], bytes] | None = None) -> Stats:
    """`cli images`. Assign keys to seeds, fill the empty ones, print the cost."""
    stats = Stats()
    lib_path = Path(lib_path) if lib_path else library_path()
    library = load_library(lib_path)

    chosen: dict[Path, str] = {}
    posts = 0
    if seed_dir:
        posts = len(seed_files(seed_dir))
        if do_assign:
            chosen = assign(seed_dir, lib_path=lib_path, dry_run=dry_run, stats=stats)
            print(f"  {'would assign' if dry_run else 'assigned'} {stats.assigned} seed(s)")
        else:
            chosen = hero_keys(seed_dir)

    if chosen:
        keys: Iterable[str] = _unique(chosen.values())
    elif seed_dir and posts:
        # Generating the whole library here would be a surprise bill for
        # someone who only meant to fill in what their posts point at.
        keys = []
        print("  no seed points at a library key yet — run with --assign first")
    else:
        # No seeds at all: `--generate` fills the library itself, which is how
        # it gets seeded before a single post points at it.
        keys = list(library)

    if do_generate:
        for key in keys:
            resolve(key, lib_path=lib_path, out_dir=out_dir, generator=generator,
                    force=force, dry_run=dry_run, use_gemini=use_gemini, stats=stats)

    if chosen and not dry_run:
        changed = sync_image_urls(chosen, load_library(lib_path))
        if changed:
            print(f"  set image_url on {changed} seed(s)")

    for line in cost_lines(stats, posts=posts, library_size=len(library), use_gemini=use_gemini):
        print(line)
    return stats


def _unique(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)
