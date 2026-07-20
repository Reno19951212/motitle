"""Unauthenticated page navigation should redirect to login, not leak raw 401 JSON.

Bug-sweep #27/#31/#28/#35/#29: /Glossary.html, /Files.html, /user.html were
@login_required (raw 401 JSON to a browser); /index.html and /favicon.ico 404'd.
They now redirect to /login.html or "/", and favicon returns 204.
"""
import pytest


@pytest.mark.real_auth
@pytest.mark.parametrize("path", ["/Glossary.html", "/Files.html", "/user.html"])
def test_protected_page_redirects_to_login_when_anon(client, path):
    r = client.get(path)
    assert r.status_code == 302, r.get_data(as_text=True)[:120]
    assert r.headers["Location"].endswith("/login.html")


def test_index_html_redirects_to_root(client):
    r = client.get("/index.html")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")


def test_favicon_returns_204(client):
    assert client.get("/favicon.ico").status_code == 204
