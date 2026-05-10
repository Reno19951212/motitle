"""Verify CORS headers allow LAN origins."""

def test_cors_allows_lan_origin():
    from app import _is_lan_origin
    assert _is_lan_origin("http://192.168.1.50:5001") is True
    assert _is_lan_origin("http://10.0.5.20") is True
    assert _is_lan_origin("http://172.20.0.5:8080") is True
    assert _is_lan_origin("http://localhost:5001") is True
    assert _is_lan_origin("http://example.com") is False
    assert _is_lan_origin("https://attacker.net") is False
