"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import io
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational
from psycopg import sql
from psycopg.errors import UndefinedTable

from app.api.v1.endpoints.cmms import _file
from app.core.config import TenantSettings
from app.db.manager import DatabaseManager
from app.services import cmms_media
from app.services.cmms_service import CmmsService
from app.services.context import ServiceContext
from app.tenancy import state
from tests.helpers import api, assert_ready


def _dms(value: float):
    value = abs(value)
    degrees = int(value)
    minutes_f = (value - degrees) * 60
    minutes = int(minutes_f)
    seconds = round((minutes_f - minutes) * 60, 2)
    return (IFDRational(degrees), IFDRational(minutes), IFDRational(int(seconds * 100), 100))


def _jpeg_with_gps(size: tuple[int, int], pad: int = 0) -> bytes:
    img = Image.new("RGB", size, (20, 80, 140))
    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = _dms(41.3874)
    gps[3] = "E"
    gps[4] = _dms(2.1686)
    gps[6] = IFDRational(12, 1)
    exif.get_ifd(0x8769)[36867] = "2024:06:01 12:30:00"
    exif[271] = "TestMake"
    exif[272] = "TestCam"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95, exif=exif)
    return buf.getvalue() + (b"\x00" * pad)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(buf, "PNG")
    return buf.getvalue()


def _pdf() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (80, 80), "red").save(buf, "PDF")
    return buf.getvalue()


def test_process_small_png_keeps_original_and_writes_thumb(tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(_png())
    result = cmms_media.process_upload(path, "image/png")
    assert result["path"] == path
    assert result["content_type"] == "image/png"
    assert result["thumbnail_path"] == tmp_path / "photo.png_thumb.jpg"
    assert result["thumbnail_path"].read_bytes()[:2] == b"\xff\xd8"
    assert "originalSize" not in result["metadata"]


def test_process_large_jpeg_compresses_and_reads_exif(tmp_path):
    original = _jpeg_with_gps((64, 64), pad=1_100_000)
    path = tmp_path / "shot.jpg"
    path.write_bytes(original)
    result = cmms_media.process_upload(path, "image/jpeg")
    assert result["size"] < len(original)
    assert result["metadata"]["originalSize"] == len(original)
    assert result["metadata"]["originalName"] == "shot.jpg"
    assert result["metadata"]["takenAt"] == "2024:06:01 12:30:00"
    assert result["metadata"]["make"] == "TestMake"
    assert result["coordinates"]["lat"] == pytest.approx(41.3874, abs=0.01)
    assert result["coordinates"]["lon"] == pytest.approx(2.1686, abs=0.01)
    assert result["coordinates"]["alt"] == pytest.approx(12)
    assert result["thumbnail_path"].exists()
    assert result["content_type"] == "image/jpeg"


def test_process_pdf_has_thumbnail_and_text_does_not(tmp_path):
    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(_pdf())
    pdf_result = cmms_media.process_upload(pdf, "application/pdf")
    assert pdf_result["path"] == pdf
    assert pdf_result["thumbnail_path"] == tmp_path / "note.pdf_thumb.jpg"
    assert pdf_result["thumbnail_path"].read_bytes()[:2] == b"\xff\xd8"

    text = tmp_path / "note.txt"
    text.write_bytes(b"hello")
    text_result = cmms_media.process_upload(text, "text/plain")
    assert text_result["thumbnail_path"] is None
    assert text.read_bytes() == b"hello"

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not-a-real-video")
    video_result = cmms_media.process_upload(video, "video/mp4")
    assert video_result["thumbnail_path"] is None
    assert video_result["size"] == len(b"not-a-real-video")


def test_process_corrupt_image_keeps_file(tmp_path):
    path = tmp_path / "bad.jpg"
    path.write_bytes(b"this is not a jpeg")
    result = cmms_media.process_upload(path, "image/jpeg")
    assert result["thumbnail_path"] is None
    assert path.read_bytes() == b"this is not a jpeg"


@pytest.fixture
def cmms_ready(client, default_params) -> bool:
    """True when the schema views exist. False when CMMS is not integrated. Skips if `cmms` is missing."""
    assert_ready(client)
    resp = client.get(api("/cmms/visits"), params={**default_params, "limit": 1})
    if resp.status_code == 500 and "cmms" in resp.text.lower():
        pytest.skip("cmms schema is not installed")
    if resp.status_code == 404 and "not integrated" in resp.text.lower():
        if not _cmms_schema_installed():
            pytest.skip("cmms schema is not installed")
        return False
    assert resp.status_code == 200, resp.text
    return True


def _tenant():
    assert state.registry is not None, "Tenant registry not initialized"
    tenant = state.registry.get("test")
    assert tenant is not None, "Tenant 'test' not loaded"
    return tenant


def _cmms_schema_installed() -> bool:
    async def _run() -> bool:
        async with _tenant().db_manager.get_db() as conn:
            assert conn is not None, "Postgres not available"
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'cmms'")
                row = await cur.fetchone()
            await conn.rollback()
        return row is not None

    return asyncio.run(_run())


def _sample_sys_code(schema: str) -> str | None:
    async def _run() -> str | None:
        async with _tenant().db_manager.get_db() as conn:
            assert conn is not None, "Postgres not available"
            row = None
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        sql.SQL(
                            "SELECT sys_code FROM {}.node WHERE sys_code IS NOT NULL AND btrim(sys_code) <> '' LIMIT 1"
                        ).format(sql.Identifier(schema))
                    )
                    row = await cur.fetchone()
            except UndefinedTable:
                row = None
            await conn.rollback()
        return row[0] if row else None

    return asyncio.run(_run())


def _hidden_read(resp, *, integrated: bool) -> None:
    assert resp.status_code == 404, resp.text
    if integrated:
        assert "not integrated" not in resp.text.lower()
    else:
        assert "not integrated" in resp.text.lower()


def _hidden_list(resp, *, integrated: bool, row_id: str, key: str) -> None:
    if not integrated:
        assert resp.status_code == 404, resp.text
        assert "not integrated" in resp.text.lower()
        return
    rows = _data(resp)[key]
    assert all(row["id"] != row_id for row in rows)


def _data(resp) -> dict:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Accepted", body
    return body["body"]["data"]


def test_create_visit_rejects_bad_dates(client, default_params):
    assert_ready(client)
    payload = {
        "type": "inspection",
        "status": "open",
        "startDate": "2024-06-02T00:00:00Z",
        "endDate": "2024-06-01T00:00:00Z",
    }
    resp = client.post(api("/cmms/visits"), params=default_params, json=payload)
    assert resp.status_code == 422, resp.text


def test_upload_over_limit_is_413(client, default_params):
    assert_ready(client)
    root = Path(os.environ["FILES_DIR"]) / "test" / "cmms"
    before = set(root.iterdir()) if root.exists() else set()
    blob = b"\x00" * (2 * 1024 * 1024 + 1)
    resp = client.post(
        api("/cmms/attachments"),
        params=default_params,
        files={"file": ("big.bin", blob, "application/octet-stream")},
    )
    assert resp.status_code == 413, resp.text
    after = set(root.iterdir()) if root.exists() else set()
    assert after == before


def test_visit_and_attachment_crud(client, default_params, cmms_ready):
    integrated = cmms_ready
    code = f"cmms-{uuid4().hex[:8]}"
    visit_payload = {
        "type": "inspection",
        "status": "open",
        "description": "seen on site",
        "properties": {"sample": "api"},
        "sysCodes": [code],
    }
    created = _data(client.post(api("/cmms/visits"), params=default_params, json=visit_payload))
    visit = created["visits"][0]
    visit_id = visit["id"]
    assert code in visit["sys_codes"]
    assert "attachments" not in visit

    photo = _data(
        client.post(
            api(f"/cmms/visits/{visit_id}/attachments"),
            params=default_params,
            files={"file": ("photo.png", _png(), "image/png")},
        )
    )
    attachment = photo["attachments"][0]
    attachment_id = attachment["id"]
    assert attachment["visit_ids"] == [visit_id]
    assert attachment["thumbnail_path"]

    listed = client.get(api("/cmms/visits"), params={**default_params, "sysCode": code})
    _hidden_list(listed, integrated=integrated, row_id=visit_id, key="visits")
    got = client.get(api(f"/cmms/visits/{visit_id}"), params=default_params)
    _hidden_read(got, integrated=integrated)

    file_resp = client.get(api(f"/cmms/attachments/{attachment_id}/file"), params=default_params)
    _hidden_read(file_resp, integrated=integrated)
    thumb = client.get(
        api(f"/cmms/visits/{visit_id}/attachments/{attachment_id}/file"),
        params={**default_params, "thumbnail": "true"},
    )
    _hidden_read(thumb, integrated=integrated)

    extra = _data(
        client.post(
            api(f"/cmms/visits/{visit_id}/attachments"),
            params=default_params,
            files={"file": ("extra.txt", b"x", "text/plain")},
        )
    )
    assert extra["attachments"][0]["visit_ids"] == [visit_id]
    assert not extra["attachments"][0].get("thumbnail_path")
    listed_files = client.get(api(f"/cmms/visits/{visit_id}/attachments"), params=default_params)
    _hidden_list(listed_files, integrated=integrated, row_id=attachment_id, key="attachments")
    _hidden_list(listed_files, integrated=integrated, row_id=extra["attachments"][0]["id"], key="attachments")

    other = f"cmms-{uuid4().hex[:8]}"
    patched = _data(
        client.patch(
            api(f"/cmms/visits/{visit_id}"),
            params=default_params,
            json={"properties": {"sample": "patched"}, "sysCodes": [other]},
        )
    )
    assert patched["visits"][0]["properties"]["sample"] == "patched"
    assert patched["visits"][0]["sys_codes"] == [other]

    deleted = _data(client.delete(api(f"/cmms/visits/{visit_id}"), params=default_params))
    assert deleted["visits"][0]["id"] == visit_id
    assert deleted["visits"][0]["sys_codes"] == [other]
    still = client.get(api(f"/cmms/attachments/{attachment_id}"), params=default_params)
    _hidden_read(still, integrated=integrated)

    direct_code = f"cmms-{uuid4().hex[:8]}"
    pdf = _data(
        client.post(
            api("/cmms/attachments"),
            params=default_params,
            data={"description": "direct", "sysCodes": [direct_code]},
            files={"file": ("note.pdf", _pdf(), "application/pdf")},
        )
    )
    text = _data(
        client.post(
            api("/cmms/attachments"),
            params=default_params,
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
    )
    by_name = {item["name"]: item for item in [pdf["attachments"][0], text["attachments"][0]]}
    assert by_name["note.pdf"]["thumbnail_path"]
    assert not by_name["note.txt"].get("thumbnail_path")
    assert direct_code in by_name["note.pdf"]["sys_codes"]

    removed = _data(client.delete(api(f"/cmms/attachments/{attachment_id}"), params=default_params))
    assert removed["attachments"][0]["id"] == attachment_id
    missing = client.get(api(f"/cmms/attachments/{attachment_id}/file"), params=default_params)
    assert missing.status_code == 404
    storage = Path(os.environ["FILES_DIR"]) / "test" / "cmms" / attachment_id
    assert not storage.exists()

    for item in [pdf["attachments"][0], text["attachments"][0], extra["attachments"][0]]:
        client.delete(api(f"/cmms/attachments/{item['id']}"), params=default_params)

    if not integrated:
        return
    feature_code = _sample_sys_code(default_params["schema"])
    if not feature_code:
        return
    member = _data(
        client.post(
            api("/cmms/visits"),
            params=default_params,
            json={
                "type": "inspection",
                "status": "open",
                "sysCodes": [feature_code],
            },
        )
    )
    member_id = member["visits"][0]["id"]
    try:
        found = _data(client.get(api("/cmms/visits"), params={**default_params, "sysCode": feature_code}))
        assert any(row["id"] == member_id for row in found["visits"])
    finally:
        client.delete(api(f"/cmms/visits/{member_id}"), params=default_params)


def test_large_jpeg_keeps_exif_coordinates(client, default_params, cmms_ready):
    blob = _jpeg_with_gps((64, 64), pad=1_100_000)
    uploaded = _data(
        client.post(
            api("/cmms/attachments"),
            params=default_params,
            files={"file": ("shot.jpg", blob, "image/jpeg")},
        )
    )
    item = uploaded["attachments"][0]
    assert item["size"] < len(blob)
    assert item["metadata"]["originalSize"] == len(blob)
    assert item["coordinates"]["lat"] == pytest.approx(41.3874, abs=0.01)
    assert item["thumbnail_path"]
    overridden = _data(
        client.post(
            api("/cmms/attachments"),
            params=default_params,
            data={"lat": "10.5", "lon": "20.25", "alt": "3"},
            files={"file": ("shot.jpg", blob, "image/jpeg")},
        )
    )
    moved = overridden["attachments"][0]
    assert moved["coordinates"]["lat"] == pytest.approx(10.5)
    assert moved["coordinates"]["lon"] == pytest.approx(20.25)
    assert moved["coordinates"]["alt"] == pytest.approx(3)
    client.delete(api(f"/cmms/attachments/{item['id']}"), params=default_params)
    client.delete(api(f"/cmms/attachments/{moved['id']}"), params=default_params)


def _set_attachment_path(attachment_id: str, path: str) -> None:
    async def _run() -> None:
        async with _tenant().db_manager.get_db() as conn:
            assert conn is not None, "Postgres not available"
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE cmms.attachment SET path = %s WHERE id = %s::uuid",
                    (path, attachment_id),
                )
            await conn.commit()

    asyncio.run(_run())


def test_files_public_url_strips_trailing_slash():
    from app.core.config import _build_tenant

    settings = _build_tenant({"FILES_PUBLIC_URL": "https://files.example/giswater/files/"})
    assert settings.files_public_url == "https://files.example/giswater/files"
    assert _build_tenant({"FILES_PUBLIC_URL": "  "}).files_public_url is None
    assert _build_tenant({}).files_dir == "data/files"
    assert _build_tenant({"FILES_DIR": "  "}).files_dir == "data/files"
    bad = _build_tenant({"FILES_MAX_UPLOAD_MB": "0"})
    with pytest.raises(ValueError, match="FILES_MAX_UPLOAD_MB"):
        bad.validate()


def test_stored_path_is_public_url_or_key_and_file_resolves_by_name(tmp_path):
    ctx = ServiceContext(
        tenant_id="test",
        db_manager=DatabaseManager(TenantSettings(), "test"),
        schema="ws_40",
        user_id=None,
        db_role=None,
    )
    stored = tmp_path / "test" / "cmms" / "att" / "my_photo.png"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"png")
    (stored.parent / "my_photo.png_thumb.jpg").write_bytes(b"\xff\xd8")

    public = CmmsService(
        ctx,
        storage_dir=tmp_path,
        max_upload_bytes=1,
        public_url="https://files.example/giswater/files/",
    )
    url = "https://files.example/giswater/files/test/cmms/att/my_photo.png"
    assert public._relative(stored) == url
    assert public._relative(stored.parent / "my_photo.png_thumb.jpg").endswith("/my_photo.png_thumb.jpg")
    assert public._resolve_stored("att", url) == stored.resolve()

    plain = CmmsService(ctx, storage_dir=tmp_path, max_upload_bytes=1)
    assert plain._relative(stored) == "test/cmms/att/my_photo.png"
    assert plain._resolve_stored("att", "test/cmms/att/my_photo.png") == stored.resolve()
    assert plain._resolve_stored("att", "https://example.com/x.jpg") == "https://example.com/x.jpg"

    redirected = _file(("https://example.com/x.jpg", "image/jpeg", "x.jpg"))
    assert redirected.status_code == 307
    assert redirected.headers["location"] == "https://example.com/x.jpg"


def test_public_url_is_stored_and_external_path_redirects(client, default_params, cmms_ready):
    if not cmms_ready:
        pytest.skip("CMMS is not integrated")
    code = _sample_sys_code(default_params["schema"])
    if not code:
        pytest.skip("no feature sys_code to publish the attachment through the CMMS view")

    tenant = _tenant()
    previous = tenant.settings
    base = "https://files.example/giswater/files"
    tenant.settings = replace(previous, files_public_url=base)
    visit_id = None
    attachment_id = None
    try:
        visit = _data(
            client.post(
                api("/cmms/visits"),
                params=default_params,
                json={"type": "inspection", "status": "open", "sysCodes": [code]},
            )
        )
        visit_id = visit["visits"][0]["id"]
        blob = _png()
        uploaded = _data(
            client.post(
                api(f"/cmms/visits/{visit_id}/attachments"),
                params=default_params,
                data={"sysCodes": [code]},
                files={"file": ("my photo.png", blob, "image/png")},
            )
        )
        item = uploaded["attachments"][0]
        attachment_id = item["id"]
        assert item["path"].startswith(f"{base}/test/cmms/")
        assert item["path"].endswith("/my_photo.png")
        assert item["thumbnail_path"].startswith(f"{base}/test/cmms/")
        assert item["thumbnail_path"].endswith("/my_photo.png_thumb.jpg")

        file_resp = client.get(api(f"/cmms/attachments/{attachment_id}/file"), params=default_params)
        assert file_resp.status_code == 200, file_resp.text
        assert file_resp.content == blob
        thumb = client.get(
            api(f"/cmms/attachments/{attachment_id}/file"),
            params={**default_params, "thumbnail": "true"},
        )
        assert thumb.status_code == 200, thumb.text
        assert thumb.content[:2] == b"\xff\xd8"

        external = "https://example.com/x.jpg"
        _set_attachment_path(attachment_id, external)
        redirected = client.get(
            api(f"/cmms/attachments/{attachment_id}/file"),
            params=default_params,
            follow_redirects=False,
        )
        assert redirected.status_code == 307, redirected.text
        assert redirected.headers["location"] == external
    finally:
        tenant.settings = previous
        if attachment_id:
            client.delete(api(f"/cmms/attachments/{attachment_id}"), params=default_params)
        if visit_id:
            client.delete(api(f"/cmms/visits/{visit_id}"), params=default_params)
