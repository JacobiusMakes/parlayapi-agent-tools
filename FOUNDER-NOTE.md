# Founder steps

Things that need a credential or a decision an agent should not make on its own.
Everything else in this repo is done.

## 1. Publish to PyPI (blocked: needs the PyPI token)

The package is ready to publish. Nothing was uploaded, because publishing needs the
PyPI API token.

```bash
python -m pip install --upgrade build twine
python -m build                  # writes dist/parlayapi_agent_tools-0.1.0*
python -m twine check dist/*
python -m twine upload dist/*    # needs PYPI_TOKEN
```

Before uploading, confirm the name `parlayapi-agent-tools` is free on PyPI. It matches
the naming of the existing `parlayapi-mcp` package, so it should be.

After the first upload, edit the Install section of README.md: delete the "Not on PyPI yet"
paragraph and its `git+https` block, and delete the "Once it is published" line so the plain
`pip install` block stands on its own.

Consider adding a `pypi-publish` GitHub Action wired to a Trusted Publisher so future
tags publish without a long lived token in the repo.

## 2. Endpoints that need a real API key to verify (untested here)

Three tools call endpoints that require a key. Their request construction is tested
against the OpenAPI document and their error handling is tested against real captured
error bodies, but no live authenticated call was made, so the response bodies are
returned as sent rather than modelled:

* `GET /v1/sports/{sport_key}/odds`
* `GET /v1/sports/{sport_key}/best-line`
* `GET /v1/historical/sports/{sport_key}/closing-odds`

One useful pass with a real key, ten minutes of work:

```bash
export PARLAY_API_KEY=...
python - <<'PY'
from parlayapi_tools import ParlayAPIClient
c = ParlayAPIClient()
print(type(c.get_odds_raw("americanfootball_nfl")))   # list or envelope?
print(c.best_line("americanfootball_nfl"))
print(c.historical_closing_odds("baseball_mlb", date="2025-08-15"))
PY
```

If `get_odds_raw` returns a bare list, the tolerant parser already handles it and
nothing changes. If any of the three returns a shape worth modelling, capture the
response into `tests/fixtures/` and add dataclasses the same way the demo endpoints
were done. Do not hand write a fixture.

## 3. Cross linking (optional, cheap)

* `/mcp` and `/docs` could mention this repo for people who want tools inside their own
  framework rather than over MCP.
* The `parlayapi-mcp` PyPI description could point here, and this README already points
  at the hosted MCP endpoint in the other direction.

## 4. Tag and release

`v0.1.0` is tagged and released on GitHub. Later releases: bump `version` in
`pyproject.toml` and `__version__` in `parlayapi_tools/core.py` together.
`tests/test_packaging.py` fails if they disagree, so a half done bump cannot ship.
