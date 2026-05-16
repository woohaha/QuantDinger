"""HTTP client wrapping QuantDinger backend.

Two endpoints used:
  POST /api/auth/login            — get JWT
  POST /api/fast-analysis/analyze — synchronous AI screening (30–90 s)

Handles transparent re-login on 401, surfaces credits/in-progress errors.
"""
from typing import Optional

import httpx


class BackendError(Exception):
    """Surface to handler so it can show a user-friendly message."""
    def __init__(self, msg: str, *, code: int | None = None, data: dict | None = None):
        super().__init__(msg)
        self.code = code
        self.data = data or {}


class QuantDingerClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 150.0):
        self.base = str(base_url).rstrip("/")
        self.username = username
        self.password = password
        self._client = httpx.AsyncClient(timeout=timeout)
        self.token: Optional[str] = None

    def set_initial_token(self, token: str | None) -> None:
        """Seed from auth_cache so we skip first login if possible."""
        self.token = token

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self) -> str:
        resp = await self._client.post(
            f"{self.base}/api/auth/login",
            json={"username": self.username, "password": self.password},
        )
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code != 200 or payload.get("code") != 1:
            raise BackendError(payload.get("msg") or f"Login HTTP {resp.status_code}",
                               code=resp.status_code, data=payload.get("data"))
        token = (payload.get("data") or {}).get("token")
        if not token:
            raise BackendError("Login response missing token", code=200, data=payload)
        self.token = token
        return token

    async def _ensure_token(self) -> str:
        if not self.token:
            await self.login()
        return self.token  # type: ignore[return-value]

    async def analyze(self, *, market: str, symbol: str, language: str = "zh-TW",
                      timeframe: str = "1D", model: str | None = None) -> dict:
        body = {"market": market, "symbol": symbol, "language": language,
                "timeframe": timeframe}
        if model:
            body["model"] = model

        resp = await self._post_authed("/api/fast-analysis/analyze", json=body)
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        code = payload.get("code")

        if resp.status_code == 200 and code == 1:
            return payload.get("data") or {}

        msg = payload.get("msg") or f"HTTP {resp.status_code}"
        data = payload.get("data") or {}

        if resp.status_code == 429:
            raise BackendError(f"in_progress: {msg}", code=429, data=data)
        if resp.status_code == 400 and "Insufficient credits" in msg:
            raise BackendError(
                f"credits insufficient (need {data.get('required')}, "
                f"have {data.get('current')})",
                code=400, data=data,
            )
        raise BackendError(msg, code=resp.status_code, data=data)

    async def _post_authed(self, path: str, *, json: dict) -> httpx.Response:
        """POST that auto re-logins once on 401."""
        token = await self._ensure_token()
        url = f"{self.base}{path}"
        resp = await self._client.post(url, json=json,
                                       headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401:
            self.token = None
            token = await self.login()
            resp = await self._client.post(url, json=json,
                                           headers={"Authorization": f"Bearer {token}"})
        return resp
