"""Non-dict JSON bodies must not crash routes into a 500 HTML page.

Regression for the bug-sweep finding: routes using `request.get_json(silent=True)
or {}` then `.get(...)` raise AttributeError (→ 500 HTML) when the body is a
truthy non-dict (JSON string / number / array / bool), violating the
"every route returns JSON {error}" contract. `request_utils.json_dict()`
coerces such bodies to {} so the route's own field validation returns a 400.
"""
import pytest

NON_DICT_BODIES = ["hello", 42, [1, 2], True]

# Representative routes flagged by the sweep that parse a JSON object body.
ROUTES = [
    ("post", "/api/glossaries/alias-lint"),
]


@pytest.mark.parametrize("body", NON_DICT_BODIES)
@pytest.mark.parametrize("method,path", ROUTES)
def test_nondict_json_body_never_500(client, method, path, body):
    resp = getattr(client, method)(path, json=body)
    assert resp.status_code != 500, (
        f"{method.upper()} {path} with body={body!r} returned 500: "
        f"{resp.get_data(as_text=True)[:120]}"
    )
    assert resp.headers["Content-Type"].startswith("application/json"), (
        f"{method.upper()} {path} with body={body!r} returned non-JSON: "
        f"{resp.headers.get('Content-Type')}"
    )


def test_json_dict_coerces_non_dict():
    """Unit: json_dict() returns {} for non-dict bodies, passthrough for dicts."""
    import app as app_module
    from request_utils import json_dict
    for body, expected in [("s", {}), (5, {}), ([1], {}), (True, {}),
                           ({"a": 1}, {"a": 1})]:
        with app_module.app.test_request_context(
                json=body, content_type="application/json"):
            assert json_dict() == expected
