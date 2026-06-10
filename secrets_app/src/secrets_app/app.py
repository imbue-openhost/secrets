import json
import re
import shlex
from contextlib import closing
from pathlib import Path

from litestar import Litestar, Request, Response, delete, get, post
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import HTTPException
from litestar.response import Template
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from litestar.template.config import TemplateConfig

from secrets_app.db import get_db, init_db


# ─── Owner Dashboard ───


@get("/", sync_to_thread=True)
def index() -> Template:
    with closing(get_db()) as db:
        secrets = [dict(r) for r in db.execute("SELECT * FROM secrets ORDER BY key").fetchall()]
    return Template(template_name="index.html", context={"secrets": secrets})


@get("/api/secrets", sync_to_thread=True)
def list_secrets() -> list[dict]:
    with closing(get_db()) as db:
        rows = db.execute("SELECT key, description, created_at, updated_at FROM secrets ORDER BY key").fetchall()
    return [dict(r) for r in rows]


@post("/api/secrets", sync_to_thread=True)
def set_secret(data: dict) -> dict:
    if not data.get("key") or "value" not in data:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="key and value are required")
    with closing(get_db()) as db:
        db.execute(
            """INSERT INTO secrets (key, value, description)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   description = excluded.description,
                   updated_at = datetime('now')""",
            (data["key"], data["value"], data.get("description", "")),
        )
        db.commit()
    return {"ok": True}


@delete("/api/secrets/{key:str}", status_code=200, sync_to_thread=True)
def delete_secret(key: str) -> dict:
    with closing(get_db()) as db:
        db.execute("DELETE FROM secrets WHERE key = ?", (key,))
        db.commit()
    return {"ok": True}


@post("/api/import", sync_to_thread=True)
def import_secrets(data: dict) -> dict:
    """Import secrets from a shell-style env file.

    Parses lines like:
        export KEY=value
        export KEY="value"
        export KEY='value'
        KEY=value
    Skips comments (#) and blank lines. Upserts all parsed key-value pairs.
    """
    if "content" not in data:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="content is required")

    parsed = _parse_env_file(data["content"])
    description = data.get("description", "")

    with closing(get_db()) as db:
        imported = 0
        skipped = 0
        for key, value in parsed:
            if not value:
                skipped += 1
                continue
            db.execute(
                """INSERT INTO secrets (key, value, description)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = datetime('now')""",
                (key, value, description),
            )
            imported += 1
        db.commit()
    return {"ok": True, "imported": imported, "skipped": skipped}


@get("/api/export", sync_to_thread=True, media_type="text/plain")
def export_secrets() -> Response:
    """Render all secrets as a shell-style env file (for download)."""
    with closing(get_db()) as db:
        rows = db.execute("SELECT key, value FROM secrets ORDER BY key").fetchall()
    body = "".join(f"export {r['key']}={shlex.quote(r['value'])}\n" for r in rows)
    return Response(
        content=body,
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="secrets.env"'},
    )


def _parse_env_file(content):
    """Parse shell-style env file. Returns list of (key, value) tuples."""
    results = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        results.append((key, value))
    return results


# ─── V2 Service API (secrets — permissions validated by provider) ───


def _parse_v2_grants(request: Request) -> tuple[set[str], bool]:
    """Read X-OpenHost-Permissions header and return (granted_keys, grant_all)."""
    perms_header = request.headers.get("X-OpenHost-Permissions", "[]")
    try:
        grants = json.loads(perms_header)
    except json.JSONDecodeError:
        return set(), False

    granted_keys: set[str] = set()
    for g in grants:
        payload = g.get("grant", {})
        if isinstance(payload, dict):
            if payload.get("key") == "*":
                return set(), True
            if "key" in payload:
                granted_keys.add(payload["key"])
    return granted_keys, False


@post("/_service_v2/get", status_code=200, sync_to_thread=True)
def service_v2_get(data: dict, request: Request) -> Response:
    """Return secret values for the requested keys (V2: provider-side permission check)."""
    requested_keys = data.get("keys", [])

    if not requested_keys:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No keys requested")

    granted_keys, grant_all = _parse_v2_grants(request)
    if not grant_all:
        missing_perms = [k for k in requested_keys if k not in granted_keys]
        if missing_perms:
            return Response(
                content={
                    "error": "permission_required",
                    "required_grant": {"grant": {"key": missing_perms[0]}},
                },
                status_code=HTTP_403_FORBIDDEN,
            )

    with closing(get_db()) as db:
        result = {}
        for key in requested_keys:
            row = db.execute("SELECT value FROM secrets WHERE key = ?", (key,)).fetchone()
            if row:
                result[key] = row["value"]

    missing = [k for k in requested_keys if k not in result]
    body: dict = {"secrets": result}
    if missing:
        body["missing"] = missing
    return Response(content=body)


@get("/_service_v2/list", sync_to_thread=True)
def service_v2_list() -> dict:
    """List available secret keys (V2: no permission check needed for names)."""
    with closing(get_db()) as db:
        rows = db.execute("SELECT key, description FROM secrets ORDER BY key").fetchall()
    return {"keys": [{"key": r["key"], "description": r["description"]} for r in rows]}


app = Litestar(
    route_handlers=[
        index,
        list_secrets,
        set_secret,
        delete_secret,
        import_secrets,
        export_secrets,
        service_v2_get,
        service_v2_list,
    ],
    template_config=TemplateConfig(
        directory=Path(__file__).parent / "templates",
        engine=JinjaTemplateEngine,
    ),
    on_startup=[lambda _app: init_db()],
)
