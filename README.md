# secrets

An [Openhost](https://github.com/imbue-openhost) app for managing environment-variable secrets. Other apps fetch secrets through the v2 services interface; the dashboard is for the owner to add/edit them.

## Grants

Consumer apps request access with permission grants (in their `openhost.toml`
`[[services.v2.consumes]]` block, or at runtime). The grant payload shapes this
service understands:

- `{ key = "NAME" }`        — access exactly that secret
- `{ key = "*" }`           — access every secret
- `{ key_prefix = "PRE_" }` — access every secret whose name starts with `PRE_`

`get` returns only the values the caller's grants cover; `list` returns key names
(no values, no grant required). Prefix grants let a consumer pull a whole
namespace (e.g. `SCULPTOR_*`) without enumerating each key or taking a blanket `*`.

## Layout

```
Dockerfile, openhost.toml, pyproject.toml    project config
secrets_app/src/secrets_app/                 package source (Litestar app, SQLite)
tests/                                       pytest smoke tests
```

## Develop

```bash
uv sync                  # install deps (incl. dev group)
uv run pytest tests/     # build container, run smoke tests against it (requires podman)
```

The smoke tests use [openhost-app-test-harness](https://github.com/imbue-openhost/openhost-app-test-harness) to build and run the app's Dockerfile under podman, fronted by a mock Openhost router.

## Deploy

```bash
oh app reload secrets --update --wait --instance personal
```
