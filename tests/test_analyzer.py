import json
import time

import pytest

from vodlint.analyzer import analyze_playlist


def analyze_text(tmp_path, text, **kwargs):
    path = tmp_path / "index.m3u8"
    path.write_text(text, encoding="utf-8")
    return analyze_playlist(str(path), **kwargs)


def rule_ids(report):
    return {finding["rule_id"] for finding in report["findings"]}


def test_duration_uses_declared_segments(tmp_path, media_text):
    report = analyze_text(tmp_path, media_text)
    assert report["playlist"]["duration"] == 11.0
    assert report["status"] == "passed"
    assert report["schema_version"] == "1"
    assert report["summary"]["scope"] == "manifests"
    assert report["summary"]["segments_checked"] == 0


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("not an HLS playlist\n", "manifest.header"),
        ("#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXT-X-ENDLIST\n", "manifest.empty"),
        ("#EXTM3U\n#EXTINF:1,\na.ts\n#EXT-X-ENDLIST\n", "manifest.target-duration"),
        (
            "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:12,\na.ts\n#EXT-X-ENDLIST\n",
            "manifest.target-duration",
        ),
        (
            "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:nan,\na.ts\n#EXT-X-ENDLIST\n",
            "manifest.segment-duration",
        ),
        (
            "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:-1,\na.ts\n#EXT-X-ENDLIST\n",
            "manifest.segment-duration",
        ),
        ("#EXTM3U\n#EXT-X-TARGETDURATION:10\na.ts\n#EXT-X-ENDLIST\n", "manifest.syntax"),
        ("#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:1,\n#EXT-X-ENDLIST\n", "manifest.syntax"),
        (
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\na.m3u8\n#EXTINF:1,\na.ts\n",
            "manifest.mixed",
        ),
        (
            "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXT-X-TARGETDURATION:2\n"
            "#EXTINF:1,\na.ts\n#EXT-X-ENDLIST\n",
            "manifest.syntax",
        ),
    ],
)
def test_invalid_manifest_fails_with_actionable_finding(tmp_path, text, rule_id):
    report = analyze_text(tmp_path, text)
    assert report["status"] == "failed"
    assert rule_id in rule_ids(report)
    finding = next(f for f in report["findings"] if f["rule_id"] == rule_id)
    assert finding["severity"] == "error"
    assert finding["message"]
    assert finding["remediation"]
    assert finding["url"]
    json.dumps(report, allow_nan=False)


def test_vod_requires_endlist_unless_live_explicitly_allowed(tmp_path, media_text):
    live = media_text.replace("#EXT-X-ENDLIST\n", "")
    assert "manifest.endlist" in rule_ids(analyze_text(tmp_path, live))
    allowed = analyze_text(tmp_path, live, require_vod=False)
    assert allowed["status"] == "passed"
    assert allowed["playlist"]["is_live"] is True


def test_round_target_duration_instead_of_comparing_raw_float(tmp_path):
    text = "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10.4,\na.ts\n#EXT-X-ENDLIST\n"
    assert analyze_text(tmp_path, text)["status"] == "passed"


def test_master_fetches_child_metadata_without_sampling(http_server, media_text):
    http_server.routes["/master.m3u8"] = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100,RESOLUTION=640x480\nmedia.m3u8\n"
    )
    http_server.routes["/media.m3u8"] = media_text
    report = analyze_playlist(http_server.url + "/master.m3u8")
    assert report["status"] == "passed"
    assert report["playlist"]["kind"] == "master"
    assert report["playlist"]["is_live"] is None
    assert report["playlist"]["segment_count"] is None
    assert report["media_playlists"][0]["duration"] == 11.0
    assert report["media_playlists"][0]["is_live"] is False
    assert report["variants"][0]["resolution"] == "640x480"
    assert report["summary"]["segment_count"] == 2
    assert http_server.counts["/media.m3u8"] == 1


def test_redirected_master_and_child_resolve_relative_segments(http_server, ts_bytes):
    http_server.routes.update(
        {
            "/start": (302, {"Location": "/master/index.m3u8"}, b""),
            "/master/index.m3u8": "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nchild\n",
            "/master/child": (302, {"Location": "/media/index.m3u8"}, b""),
            "/media/index.m3u8": (
                "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\na.ts\n#EXT-X-ENDLIST\n"
            ),
            "/media/a.ts": ts_bytes,
        }
    )
    report = analyze_playlist(http_server.url + "/start", segments_to_sample=1)
    assert report["status"] == "passed"
    assert report["segment_probes"][0]["url"] == http_server.url + "/media/a.ts"


def test_nested_local_master_and_segment_paths(tmp_path, ts_bytes, media_text):
    subdir = tmp_path / "media with spaces"
    subdir.mkdir()
    (subdir / "index.m3u8").write_text(media_text)
    (subdir / "a.ts").write_bytes(ts_bytes)
    root = tmp_path / "master.m3u8"
    root.write_text("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nmedia with spaces/index.m3u8\n")
    report = analyze_playlist(str(root), segments_to_sample=1)
    assert report["status"] == "passed"
    assert report["segment_probes"][0]["container"] == "ts"
    assert report["summary"]["segments_checked"] == 1
    assert report["summary"]["all_segments_sampled"] is False


def test_local_byte_ranges_include_implicit_offset(tmp_path, ts_bytes):
    (tmp_path / "all.ts").write_bytes(ts_bytes + bytes.fromhex("fff15080013ffc0000"))
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-VERSION:4\n#EXT-X-TARGETDURATION:1\n"
        "#EXTINF:1,\n#EXT-X-BYTERANGE:376@0\nall.ts\n"
        "#EXTINF:1,\n#EXT-X-BYTERANGE:9\nall.ts\n#EXT-X-ENDLIST\n",
        segments_to_sample=2,
    )
    assert report["status"] == "passed"
    assert [p["size_bytes"] for p in report["segment_probes"]] == [376, 9]
    assert [p["container"] for p in report["segment_probes"]] == ["ts", "adts"]
    assert report["segment_probes"][1]["byte_range"] == {"offset": 376, "length": 9}


def test_invalid_implicit_range_fails_even_without_sampling(tmp_path):
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-VERSION:4\n#EXT-X-TARGETDURATION:1\n"
        "#EXTINF:1,\n#EXT-X-BYTERANGE:376\na.ts\n#EXT-X-ENDLIST\n",
    )
    assert "manifest.byterange" in rule_ids(report)
    assert report["status"] == "failed"


def test_failed_child_does_not_discard_valid_child(http_server, media_text):
    http_server.routes["/master"] = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nmissing\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=200\ngood\n"
    )
    http_server.routes["/good"] = media_text
    report = analyze_playlist(http_server.url + "/master")
    assert report["status"] == "error"
    assert len(report["errors"]) == 1
    assert report["media_playlists"][0]["duration"] == 11.0
    assert report["summary"]["inspection_complete"] is False


def test_failed_segment_preserves_and_continues_other_probes(tmp_path, media_text, ts_bytes):
    (tmp_path / "b.ts").write_bytes(ts_bytes)
    report = analyze_text(tmp_path, media_text, segments_to_sample=2)
    assert report["status"] == "error"
    assert [p["status"] for p in report["segment_probes"]] == ["error", "inspected"]
    assert report["summary"]["segments_checked"] == 1


def test_unsupported_sample_fails_default_threshold(tmp_path, media_text):
    (tmp_path / "a.ts").write_bytes(b"not media")
    report = analyze_text(tmp_path, media_text, segments_to_sample=1)
    assert report["status"] == "failed"
    assert "segment.unsupported" in rule_ids(report)
    assert report["summary"]["inspection_complete"] is False
    assert report["summary"]["segments_unsupported"] == 1
    permissive = analyze_text(tmp_path, media_text, segments_to_sample=1, fail_on="error")
    assert permissive["status"] == "passed"
    assert permissive["summary"]["inspection_complete"] is False
    assert permissive["summary"]["segments_unsupported"] == 1


def test_encrypted_sample_is_explicitly_skipped(tmp_path):
    report = analyze_text(
        tmp_path,
        '#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n'
        "#EXTINF:1,\nsecret.ts\n#EXT-X-ENDLIST\n",
        segments_to_sample=1,
    )
    assert report["status"] == "failed"
    assert "segment.encrypted" in rule_ids(report)
    assert report["segment_probes"][0]["status"] == "skipped"
    assert report["errors"] == []  # Neither a missing key nor ciphertext was fetched.


@pytest.mark.parametrize("child", [False, True])
def test_timeout_applies_to_root_and_child_playlists(http_server, child):
    def slow(request, count):
        time.sleep(0.15)
        return b"#EXTM3U\n"

    http_server.routes["/slow"] = slow
    http_server.routes["/master"] = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nslow\n"
    report = analyze_playlist(
        http_server.url + ("/master" if child else "/slow"),
        http_timeout_seconds=0.02,
        http_retries=0,
    )
    assert report["status"] == "error"
    assert report["errors"][0]["code"] == "resource.fetch"


def test_signed_urls_and_credentials_are_redacted(http_server, media_text):
    http_server.routes["/media?token=secret"] = media_text
    report = analyze_playlist(http_server.url + "/media?token=secret")
    assert "secret" not in json.dumps(report)
    assert "REDACTED" in report["playlist"]["url"]


def test_invalid_utf8_is_a_manifest_finding(tmp_path):
    path = tmp_path / "bad.m3u8"
    path.write_bytes(b"#EXTM3U\n\xff")
    report = analyze_playlist(str(path))
    assert report["status"] == "failed"
    assert "manifest.encoding" in rule_ids(report)


@pytest.mark.parametrize("sample_count", [0, 1])
def test_whitespace_segment_uri_fails_without_crashing(tmp_path, sample_count):
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n   \n#EXT-X-ENDLIST\n",
        segments_to_sample=sample_count,
    )
    assert report["status"] == "failed"
    assert "manifest.syntax" in rule_ids(report)


def test_blank_byte_range_is_invalid_even_without_sampling(tmp_path):
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-VERSION:4\n#EXT-X-TARGETDURATION:1\n"
        "#EXTINF:1,\n#EXT-X-BYTERANGE:\na.ts\n#EXT-X-ENDLIST\n",
    )
    assert report["status"] == "failed"
    assert "manifest.byterange" in rule_ids(report)


def test_invalid_child_cannot_claim_complete_sampling(http_server, ts_bytes):
    http_server.routes.update(
        {
            "/master": "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nbad\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=200\ngood\n",
            "/bad": b"invalid",
            "/good": "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\na.ts\n#EXT-X-ENDLIST\n",
            "/a.ts": ts_bytes,
        }
    )
    report = analyze_playlist(http_server.url + "/master", segments_to_sample=1)
    assert report["status"] == "failed"
    assert report["summary"]["segments_checked"] == 1
    assert report["summary"]["inspection_complete"] is False
    assert report["summary"]["all_segments_sampled"] is False


def test_malformed_uri_does_not_abort_other_children(http_server, ts_bytes):
    http_server.routes.update(
        {
            "/master": "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nbad\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=200\ngood\n",
            "/bad": "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://[bad\n"
            "#EXT-X-ENDLIST\n",
            "/good": "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\na.ts\n#EXT-X-ENDLIST\n",
            "/a.ts": ts_bytes,
        }
    )
    report = analyze_playlist(http_server.url + "/master", segments_to_sample=1)
    assert report["status"] == "failed"
    assert "manifest.syntax" in rule_ids(report)
    assert report["summary"]["segments_checked"] == 1


def test_duration_overflow_is_a_finding_not_a_json_crash(tmp_path):
    target = "1" + "0" * 308
    report = analyze_text(
        tmp_path,
        f"#EXTM3U\n#EXT-X-TARGETDURATION:{target}\n"
        "#EXTINF:9e307,\na.ts\n#EXTINF:9e307,\nb.ts\n#EXT-X-ENDLIST\n",
    )
    assert report["status"] == "failed"
    assert "manifest.segment-duration" in rule_ids(report)
    json.dumps(report, allow_nan=False)


def test_uri_less_master_cannot_pass(tmp_path):
    report = analyze_text(
        tmp_path,
        '#EXTM3U\n#EXT-X-MEDIA:TYPE=CLOSED-CAPTIONS,GROUP-ID="cc",'
        'NAME="English",INSTREAM-ID="CC1"\n',
    )
    assert report["status"] == "failed"
    assert "manifest.empty" in rule_ids(report)


def test_init_dependent_sample_is_skipped_with_warning(tmp_path):
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-VERSION:6\n#EXT-X-TARGETDURATION:1\n"
        '#EXT-X-MAP:URI="init.mp4"\n#EXTINF:1,\na.m4s\n#EXT-X-ENDLIST\n',
        segments_to_sample=1,
    )
    assert report["status"] == "failed"
    assert "segment.unsupported" in rule_ids(report)
    assert report["segment_probes"][0]["status"] == "skipped"
    assert report["summary"]["segments_unsupported"] == 0
    assert report["errors"] == []


@pytest.mark.parametrize("fail_on", ["warning", "error"])
def test_mixed_sample_outcomes_have_distinct_reconciling_counts(tmp_path, ts_bytes, fail_on):
    (tmp_path / "supported.ts").write_bytes(ts_bytes)
    (tmp_path / "unknown.bin").write_bytes(b"not a media container")
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-TARGETDURATION:1\n"
        "#EXTINF:1,\nsupported.ts\n#EXTINF:1,\nunknown.bin\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="key"\n#EXTINF:1,\nencrypted.ts\n'
        "#EXT-X-KEY:METHOD=NONE\n#EXTINF:1,\nmissing.ts\n#EXT-X-ENDLIST\n",
        segments_to_sample=4,
        fail_on=fail_on,
    )
    summary = report["summary"]
    counts = [
        summary[field]
        for field in (
            "segments_checked",
            "segments_unsupported",
            "segments_skipped",
            "segments_failed",
        )
    ]
    assert counts == [1, 1, 1, 1]
    assert summary["segments_requested"] == sum(counts) == 4
    assert [probe["status"] for probe in report["segment_probes"]] == [
        "inspected",
        "unsupported",
        "skipped",
        "error",
    ]
    assert report["schema_version"] == "1"
    assert report["status"] == "error"
    assert summary["inspection_complete"] is False
    assert summary["all_segments_sampled"] is False


def test_no_sampling_reports_zero_unsupported(tmp_path, media_text):
    report = analyze_text(tmp_path, media_text)
    assert report["summary"]["segments_unsupported"] == 0
    assert report["summary"]["segments_requested"] == 0
    assert report["segment_probes"] == []
    assert report["status"] == "passed"


def test_shared_http_session_preserves_cookies(http_server, media_text):
    http_server.routes["/master"] = (
        200,
        {"Set-Cookie": "session=ok; Path=/"},
        b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nmedia\n",
    )
    http_server.routes["/media"] = lambda request, count: (
        media_text.encode()
        if request.headers.get("Cookie") == "session=ok"
        else (403, {}, b"no cookie")
    )
    assert analyze_playlist(http_server.url + "/master")["status"] == "passed"


def test_malformed_master_reference_preserves_later_valid_child(http_server, media_text):
    http_server.routes["/master"] = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nhttp://[bad\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=200\ngood\n"
    )
    http_server.routes["/good"] = media_text
    report = analyze_playlist(http_server.url + "/master")
    assert report["status"] == "failed"
    assert report["media_playlists"][0]["duration"] == 11.0
    assert report["summary"]["inspection_complete"] is False


def test_oversize_target_duration_is_a_finding(tmp_path):
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-TARGETDURATION:" + "9" * 400 + "\n#EXTINF:1,\na.ts\n#EXT-X-ENDLIST\n",
    )
    assert report["status"] == "failed"
    assert "manifest.target-duration" in rule_ids(report)
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    "declaration",
    ['#EXT-X-KEY:URI="key"', "#EXT-X-KEY:METHOD=AES-128", '#EXT-X-MAP:BYTERANGE="10@0"'],
)
def test_incomplete_encryption_or_init_declarations_are_manifest_errors(tmp_path, declaration):
    report = analyze_text(
        tmp_path,
        "#EXTM3U\n#EXT-X-VERSION:6\n#EXT-X-TARGETDURATION:1\n"
        f"{declaration}\n#EXTINF:1,\na.ts\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="valid.key"\n'
        "#EXTINF:1,\nb.ts\n#EXT-X-ENDLIST\n",
    )
    assert report["status"] == "failed"
    assert "manifest.syntax" in rule_ids(report)
