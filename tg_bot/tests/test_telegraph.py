"""Test TelegraphClient against the api.telegra.ph contract using respx."""
import httpx
import pytest
import respx

from tg_bot.services.telegraph import TelegraphClient, TelegraphError


BASE = "https://api.telegra.ph"


@respx.mock
async def test_create_account_returns_token():
    respx.post(f"{BASE}/createAccount").mock(return_value=httpx.Response(
        200, json={"ok": True, "result": {
            "access_token": "ATK",
            "auth_url": "https://edit.telegra.ph/auth/abc",
            "short_name": "QD",
            "author_name": "QuantDinger Bot",
            "author_url": "https://t.me/x",
        }}))
    c = TelegraphClient()
    result = await c.create_account(short_name="QD",
                                    author_name="QuantDinger Bot",
                                    author_url="https://t.me/x")
    assert result["access_token"] == "ATK"
    assert result["short_name"] == "QD"
    await c.aclose()


@respx.mock
async def test_create_page_returns_url():
    respx.post(f"{BASE}/createPage").mock(return_value=httpx.Response(
        200, json={"ok": True, "result": {
            "path": "Title-05-16",
            "url": "https://telegra.ph/Title-05-16",
            "title": "Title",
            "description": "",
            "author_name": "QuantDinger Bot",
        }}))
    c = TelegraphClient(access_token="ATK")
    result = await c.create_page(title="Title",
                                 content=[{"tag": "p", "children": ["hi"]}],
                                 author_name="QuantDinger Bot",
                                 author_url="")
    assert result["url"] == "https://telegra.ph/Title-05-16"
    assert result["path"] == "Title-05-16"
    await c.aclose()


@respx.mock
async def test_edit_page_returns_url():
    respx.post(f"{BASE}/editPage/foo-05-16").mock(return_value=httpx.Response(
        200, json={"ok": True, "result": {
            "path": "foo-05-16",
            "url": "https://telegra.ph/foo-05-16",
        }}))
    c = TelegraphClient(access_token="ATK")
    result = await c.edit_page(path="foo-05-16", title="Title",
                               content=[{"tag": "p", "children": ["hi"]}],
                               author_name="QD", author_url="")
    assert result["url"] == "https://telegra.ph/foo-05-16"
    await c.aclose()


@respx.mock
async def test_create_page_error_raises():
    respx.post(f"{BASE}/createPage").mock(return_value=httpx.Response(
        200, json={"ok": False, "error": "ACCESS_TOKEN_INVALID"}))
    c = TelegraphClient(access_token="bad")
    with pytest.raises(TelegraphError) as exc:
        await c.create_page(title="T", content=[{"tag": "p", "children": ["x"]}],
                            author_name="QD", author_url="")
    assert "ACCESS_TOKEN_INVALID" in str(exc.value)
    await c.aclose()


@respx.mock
async def test_create_page_serializes_content_to_json():
    """Telegraph requires content as JSON string, not nested form."""
    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["data"] = dict(request.url.params) if request.url.params else None
        body = request.read().decode("utf-8")
        captured["body"] = body
        return httpx.Response(200, json={
            "ok": True, "result": {"path": "p", "url": "https://telegra.ph/p"}
        })

    respx.post(f"{BASE}/createPage").mock(side_effect=_handler)

    c = TelegraphClient(access_token="ATK")
    await c.create_page(title="T",
                        content=[{"tag": "p", "children": ["hi"]}],
                        author_name="QD", author_url="")
    # content field should appear as a JSON-encoded string within the form body
    assert "content=" in captured["body"]
    assert "%22tag%22" in captured["body"] or '"tag"' in captured["body"]
    await c.aclose()
