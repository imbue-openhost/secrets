# secrets

An [Openhost](https://github.com/imbue-openhost) app for managing environment-variable secrets. Other apps fetch secrets through the v2 services interface; the dashboard is for the owner to add/edit them.

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
