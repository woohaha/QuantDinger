"""Test QuantDingerClient using respx to mock backend HTTP."""
import httpx
import pytest
import respx

from tg_bot.services.quantdinger import QuantDingerClient, BackendError


BASE = "http://backend:5000"


@pytest.fixture
def client():
    return QuantDingerClient(base_url=BASE, username="u", password="pw", timeout=5)


@respx.mock
async def test_login_success(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "msg": "ok",
                   "data": {"token": "TKN", "userinfo": {"id": 1}}}))
    token = await client.login()
    assert token == "TKN"
    assert client.token == "TKN"
    await client.aclose()


@respx.mock
async def test_login_invalid_credentials(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        401, json={"code": 0, "msg": "Invalid credentials", "data": None}))
    with pytest.raises(BackendError) as exc:
        await client.login()
    assert "Invalid credentials" in str(exc.value)
    await client.aclose()


@respx.mock
async def test_analyze_success(client, fake_analysis_json):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "data": {"token": "TKN"}}))
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(return_value=httpx.Response(
        200, json={"code": 1, "msg": "success", "data": fake_analysis_json}))

    result = await client.analyze(market="CNStock", symbol="601766",
                                  language="zh-TW", timeframe="1D")
    assert result["decision"] == "BUY"
    assert result["symbol"] == "601766"
    await client.aclose()


@respx.mock
async def test_analyze_relogin_on_401(client, fake_analysis_json):
    """Token expired mid-flight: client should re-login transparently."""
    respx.post(f"{BASE}/api/auth/login").mock(side_effect=[
        httpx.Response(200, json={"code": 1, "data": {"token": "OLD"}}),
        httpx.Response(200, json={"code": 1, "data": {"token": "NEW"}}),
    ])
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(side_effect=[
        httpx.Response(401, json={"code": 401, "msg": "Token invalid"}),
        httpx.Response(200, json={"code": 1, "data": fake_analysis_json}),
    ])
    result = await client.analyze(market="CNStock", symbol="601766",
                                  language="zh-TW", timeframe="1D")
    assert result["decision"] == "BUY"
    assert client.token == "NEW"
    await client.aclose()


@respx.mock
async def test_analyze_429_inflight_raises(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "data": {"token": "TKN"}}))
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(return_value=httpx.Response(
        429, json={"code": 0, "msg": "Analysis already in progress",
                   "data": {"in_progress": True}}))
    with pytest.raises(BackendError) as exc:
        await client.analyze(market="CNStock", symbol="601766",
                             language="zh-TW", timeframe="1D")
    assert "in_progress" in str(exc.value).lower() or "已有" in str(exc.value) or "in progress" in str(exc.value).lower()
    await client.aclose()


@respx.mock
async def test_analyze_insufficient_credits(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "data": {"token": "TKN"}}))
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(return_value=httpx.Response(
        400, json={"code": 0, "msg": "Insufficient credits",
                   "data": {"required": 10, "current": 3, "shortage": 7}}))
    with pytest.raises(BackendError) as exc:
        await client.analyze(market="CNStock", symbol="601766",
                             language="zh-TW", timeframe="1D")
    assert "credits" in str(exc.value).lower()
    await client.aclose()
