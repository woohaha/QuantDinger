"""Telegraph API client (https://telegra.ph/api).

Methods used:
  POST /createAccount   (no token)  -> bootstrap once on first run
  POST /createPage      (token)     -> write a new article
  POST /editPage/<path> (token)     -> optional re-publish under same path

All requests are POST with form-encoded body. `content` is a JSON-encoded
string. Returns dict on success; raises TelegraphError on `ok: false`.
"""
import json
from typing import Any

import httpx


BASE = "https://api.telegra.ph"


class TelegraphError(Exception):
    pass


class TelegraphClient:
    def __init__(self, access_token: str | None = None, timeout: float = 30.0):
        self.access_token = access_token
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_account(self, *, short_name: str, author_name: str,
                             author_url: str) -> dict:
        form = {"short_name": short_name[:32],
                "author_name": author_name[:128],
                "author_url":  (author_url or "")[:512]}
        return await self._call("createAccount", form)

    async def create_page(self, *, title: str, content: list, author_name: str,
                          author_url: str, return_content: bool = False) -> dict:
        form = self._build_page_form(title=title, content=content,
                                     author_name=author_name, author_url=author_url,
                                     return_content=return_content)
        return await self._call("createPage", form)

    async def edit_page(self, *, path: str, title: str, content: list,
                        author_name: str, author_url: str,
                        return_content: bool = False) -> dict:
        form = self._build_page_form(title=title, content=content,
                                     author_name=author_name, author_url=author_url,
                                     return_content=return_content)
        return await self._call(f"editPage/{path}", form)

    def _build_page_form(self, *, title: str, content: list, author_name: str,
                         author_url: str, return_content: bool) -> dict[str, Any]:
        if not self.access_token:
            raise TelegraphError("access_token required")
        return {
            "access_token": self.access_token,
            "title": title[:256],
            "content": json.dumps(content, ensure_ascii=False),
            "author_name": (author_name or "")[:128],
            "author_url":  (author_url or "")[:512],
            "return_content": "true" if return_content else "false",
        }

    async def _call(self, method: str, form: dict) -> dict:
        resp = await self._client.post(f"{BASE}/{method}", data=form)
        if resp.status_code != 200:
            raise TelegraphError(f"HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as e:
            raise TelegraphError(f"bad JSON: {e}") from e
        if not payload.get("ok"):
            raise TelegraphError(payload.get("error") or "unknown telegraph error")
        return payload.get("result") or {}
