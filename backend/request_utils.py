"""Small request-parsing helpers shared by app.py and the route blueprints."""
from flask import request


def json_dict():
    """Return the request JSON body as a dict.

    Mirrors the old ``request.get_json(silent=True) or {}`` idiom but coerces a
    non-dict body (a JSON string / number / array / bool) to ``{}`` instead of
    letting a later ``.get()`` raise ``AttributeError`` — which Flask turns into
    a 500 HTML page, violating the "every route returns JSON ``{error}``"
    contract. Routes keep their own field validation and return their own 400s.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}
