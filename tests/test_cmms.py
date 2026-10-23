"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import io
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.services import cmms_media
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
    assert result["thumbnail_path"] == tmp_path / "thumb.jpg"
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
    assert pdf_result["thumbnail_path"] == tmp_path / "thumb.jpg"
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
def cmms_ready(client, default_params):
    assert_ready(client)
    resp = client.get(api("/cmms/visits"), params={**default_params, "limit": 1})
    if resp.status_code == 500 and "cmms" in resp.text.lower():
        pytest.skip("cmms schema is not installed")
    assert resp.status_code == 200, resp.text


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
    resp = client.post(api("/cmms/visits"), params=default_params, data={"visit": json.dumps(payload)})
    assert resp.status_code == 422, resp.text


def test_upload_over_limit_is_413(client, default_params):
    assert_ready(client)
    root = Path(os.environ["CMMS_STORAGE_DIR"]) / "test"
    before = set(root.iterdir()) if root.exists() else set()
    blob = b"\x00" * (2 * 1024 * 1024 + 1)
    resp = client.post(
        api("/cmms/attachments"),
        params=default_params,
        files=[("files", ("big.bin", blob, "application/octet-stream"))],
    )
    assert resp.status_code == 413, resp.text
    after = set(root.iterdir()) if root.exists() else set()
    assert after == before


def test_visit_and_attachment_crud(client, default_params, cmms_ready):
    code = f"cmms-{uuid4().hex[:8]}"
    visit_payload = {
        "type": "inspection",
        "status": "open",
        "description": "seen on site",
        "properties": {"sample": "api"},
        "sysCodes": [code],
    }
    created = _data(
        client.post(
            api("/cmms/visits"),
            params=default_params,
            data={"visit": json.dumps(visit_payload)},
            files=[("files", ("photo.png", _png(), "image/png"))],
        )
    )
    visit = created["visits"][0]
    visit_id = visit["id"]
    assert code in visit["sys_codes"]
    attachment = visit["attachments"][0]
    attachment_id = attachment["id"]
    assert attachment["thumbnail_path"]

    listed = _data(client.get(api("/cmms/visits"), params={**default_params, "sysCode": code}))
    assert any(row["id"] == visit_id for row in listed["visits"])

    file_resp = client.get(api(f"/cmms/attachments/{attachment_id}/file"), params=default_params)
    assert file_resp.status_code == 200, file_resp.text
    assert file_resp.content == _png()
    thumb = client.get(
        api(f"/cmms/visits/{visit_id}/attachments/{attachment_id}/file"),
        params={**default_params, "thumbnail": "true"},
    )
    assert thumb.status_code == 200, thumb.text
    assert thumb.content[:2] == b"\xff\xd8"

    extra = _data(
        client.post(
            api(f"/cmms/visits/{visit_id}/attachments"),
            params=default_params,
            files=[("files", ("extra.txt", b"x", "text/plain"))],
        )
    )
    assert extra["attachments"][0]["visit_ids"] == [visit_id]
    assert not extra["attachments"][0].get("thumbnail_path")

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
    still = client.get(api(f"/cmms/attachments/{attachment_id}"), params=default_params)
    assert still.status_code == 200, still.text

    direct_code = f"cmms-{uuid4().hex[:8]}"
    uploaded = _data(
        client.post(
            api("/cmms/attachments"),
            params=default_params,
            data={"meta": json.dumps({"sysCodes": [direct_code], "description": "direct"})},
            files=[
                ("files", ("note.pdf", _pdf(), "application/pdf")),
                ("files", ("note.txt", b"hello", "text/plain")),
            ],
        )
    )
    by_name = {item["name"]: item for item in uploaded["attachments"]}
    assert by_name["note.pdf"]["thumbnail_path"]
    assert not by_name["note.txt"].get("thumbnail_path")
    assert direct_code in by_name["note.pdf"]["sys_codes"]

    removed = _data(client.delete(api(f"/cmms/attachments/{attachment_id}"), params=default_params))
    assert removed["attachments"][0]["id"] == attachment_id
    missing = client.get(api(f"/cmms/attachments/{attachment_id}/file"), params=default_params)
    assert missing.status_code == 404
    storage = Path(os.environ["CMMS_STORAGE_DIR"]) / "test" / attachment_id
    assert not storage.exists()

    for item in [*uploaded["attachments"], *extra["attachments"]]:
        client.delete(api(f"/cmms/attachments/{item['id']}"), params=default_params)


def test_large_jpeg_keeps_exif_coordinates(client, default_params, cmms_ready):
    blob = _jpeg_with_gps((64, 64), pad=1_100_000)
    uploaded = _data(
        client.post(
            api("/cmms/attachments"),
            params=default_params,
            files=[("files", ("shot.jpg", blob, "image/jpeg"))],
        )
    )
    item = uploaded["attachments"][0]
    assert item["size"] < len(blob)
    assert item["metadata"]["originalSize"] == len(blob)
    assert item["coordinates"]["lat"] == pytest.approx(41.3874, abs=0.01)
    assert item["thumbnail_path"]
    client.delete(api(f"/cmms/attachments/{item['id']}"), params=default_params)
