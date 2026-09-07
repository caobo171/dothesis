"""DataForSEO Google Ads search volume, the bulk measurement source.

Up to 1,000 keywords per request against
`/v3/keywords_data/google_ads/search_volume/live`, Vietnam (`location_code
2704`), Vietnamese (`language_code vi`). Every response carries a `cost` field
in USD and this client returns the total, because the rule in the pipeline
skill is that the five-keyword probe prints its cost before any bulk call.

Google Ads volume carries no difficulty, so `kd` comes back empty and the
difficulty cut in `gate` simply never fires on rows measured here. That is
correct, not an omission: only OpenSEO-measured rows have a difficulty to cut on.
"""
from __future__ import annotations

import os

BASE_URL = "https://api.dataforseo.com/v3"
ENDPOINT = "/keywords_data/google_ads/search_volume/live"
LOCATION_CODE = 2704  # Vietnam
LANGUAGE_CODE = "vi"
BATCH_SIZE = 1000  # the endpoint's documented per-task maximum
TIMEOUT_S = 180
OK_STATUS = 20000


class DataForSEOError(RuntimeError):
    pass


class DataForSEOClient:
    def __init__(self, login: str | None = None, password: str | None = None, http=None):
        self.login = login if login is not None else os.getenv("DATAFORSEO_LOGIN", "")
        self.password = password if password is not None else os.getenv("DATAFORSEO_PASSWORD", "")
        if not self.login or not self.password:
            raise DataForSEOError(
                "DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set to measure demand")
        self._http = http  # injected in tests; nothing here ever touches the network in CI

    @property
    def http(self):
        if self._http is None:
            import httpx  # noqa: PLC0415 — keep httpx off the import path of qa.py

            self._http = httpx.Client(timeout=TIMEOUT_S)
        return self._http

    def search_volume(self, keywords: list[str]) -> tuple[dict[str, int | None], float]:
        """{keyword: monthly volume or None}, and the total API cost in USD.

        A keyword the endpoint has no data for comes back with
        `search_volume: null`. That is a real answer ("nobody searches this")
        and it is preserved as None rather than coerced to 0, so `gate` can say
        `no volume` rather than `volume 0` in the evidence file.
        """
        volumes: dict[str, int | None] = {}
        cost = 0.0
        unique = list(dict.fromkeys(k for k in keywords if k))
        for start in range(0, len(unique), BATCH_SIZE):
            batch = unique[start:start + BATCH_SIZE]
            payload = [{
                "keywords": batch,
                "location_code": LOCATION_CODE,
                "language_code": LANGUAGE_CODE,
                "search_partners": False,
            }]
            response = self.http.post(BASE_URL + ENDPOINT, json=payload,
                                      auth=(self.login, self.password),
                                      headers={"Content-Type": "application/json"},
                                      timeout=TIMEOUT_S)
            if response.status_code >= 400:
                # DataForSEO puts the real reason in the body, not the status
                # line. A bare `402 Unknown` traceback sent someone hunting for
                # a code bug when the account had simply run out of balance
                # (status_code 40200, "Payment Required", on 2026-09-08).
                detail = ""
                try:
                    body = response.json()
                    detail = f": {body.get('status_code')} {body.get('status_message')}"
                except ValueError:
                    detail = f": {response.text[:200]}"
                raise DataForSEOError(
                    f"DataForSEO returned HTTP {response.status_code}{detail}")
            body = response.json()
            if body.get("status_code") != OK_STATUS:
                raise DataForSEOError(
                    f"DataForSEO refused the request: "
                    f"{body.get('status_code')} {body.get('status_message')}")
            cost += float(body.get("cost") or 0.0)
            for task in body.get("tasks") or []:
                if task.get("status_code") != OK_STATUS:
                    raise DataForSEOError(
                        f"DataForSEO task failed: "
                        f"{task.get('status_code')} {task.get('status_message')}")
                for item in task.get("result") or []:
                    keyword = item.get("keyword")
                    if keyword is None:
                        continue
                    raw = item.get("search_volume")
                    volumes[keyword] = None if raw is None else int(raw)
        return volumes, cost
