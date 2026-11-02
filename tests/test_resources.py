import json

import pytest

from vodlint.analyzer import analyze_playlist
from vodlint.cli import main


def master(*uris):
    return "#EXTM3U\n" + "".join(f"#EXT-X-STREAM-INF:BANDWIDTH=1000\n{uri}\n" for uri in uris)


def media(*uris, tags=""):
    return (
        "#EXTM3U\n#EXT-X-VERSION:4\n#EXT-X-TARGETDURATION:10\n"
        + tags
        + "".join(f"#EXTINF:1,\n{uri}\n" for uri in uris)
        + "#EXT-X-ENDLIST\n"
    )


def test_partial_inventory_preserves_failures_order_duplicates_and_redaction(http_server, ts_bytes):
    server = http_server
    server.routes["/root?token=root-secret"] = master(
        "bad?token=bad-secret", "good?token=good-secret", "good?token=good-secret"
    )
    server.routes["/bad?token=bad-secret"] = "not HLS"
    server.routes["/good?token=good-secret"] = media(
        "ok.ts?token=sample-secret#fragment-secret", "missing.ts?token=missing-secret"
    )
    server.routes["/ok.ts?token=sample-secret"] = ts_bytes
    source = server.url.replace("http://", "http://user:password-secret@")
    source += "/root?token=root-secret#root-fragment-secret"
    report = analyze_playlist(source, segments_to_sample=2, http_retries=0)
    resources = report["resources"]
    assert [r["id"] for r in resources] == [0, 1, 2, 3, 4, 5]
    assert [r["kind"] for r in resources] == [
        "manifest",
        "manifest",
        "manifest",
        "segment",
        "segment",
        "manifest",
    ]
    assert [r["status"] for r in resources] == [
        "validated",
        "invalid",
        "validated",
        "inspected",
        "error",
        "duplicate",
    ]
    assert [r["reason"] for r in resources] == [
        None,
        "invalid_manifest",
        None,
        None,
        "fetch_error",
        None,
    ]
    assert [r["parent_id"] for r in resources] == [None, 0, 0, 2, 2, 0]
    assert [r["segment_index"] for r in resources] == [None, None, None, 0, 1, None]
    assert resources[5]["duplicate_of"] == 2
    assert resources[1]["effective_url"] == server.url + "/bad?REDACTED"
    assert resources[4]["effective_url"] is None
    assert resources[5]["effective_url"] is None
    assert server.counts["/good?token=good-secret"] == 1
    assert server.counts["/ok.ts?token=sample-secret"] == 1
    serialized = json.dumps(report)
    assert "-secret" not in serialized
    assert "user:" not in serialized
    assert report["schema_version"] == "1"
    assert report["status"] == "error"
    assert report["summary"]["manifests_checked"] == 3
    assert report["summary"]["segments_checked"] == 1
    assert report["summary"]["segments_failed"] == 1
    assert report["summary"]["inspection_complete"] is False
    assert report["summary"]["all_segments_sampled"] is False
    assert analyze_playlist(source, 2, http_retries=0)["resources"] == resources


def test_duplicate_failed_manifest_is_not_retried_or_claimed_valid(http_server):
    http_server.routes["/root"] = master("missing", "missing")
    report = analyze_playlist(http_server.url + "/root", http_retries=0)
    assert [r["status"] for r in report["resources"]] == ["validated", "error", "duplicate"]
    assert report["resources"][2]["duplicate_of"] == 1
    assert http_server.counts["/missing"] == 1


def test_manifest_only_inventory_excludes_unrequested_samples_and_keeps_distinct_queries(
    http_server,
):
    http_server.routes["/root"] = master("child?one", "child?two")
    http_server.routes["/child?one"] = media("unfetched.ts")
    http_server.routes["/child?two"] = media("unfetched.ts")
    report = analyze_playlist(http_server.url + "/root")
    assert [r["status"] for r in report["resources"]] == ["validated"] * 3
    assert report["resources"][1]["url"] == report["resources"][2]["url"]
    assert len(http_server.seen) == 3
    assert report["segment_probes"] == []


@pytest.mark.parametrize(
    ("text", "status", "reason"),
    [
        (b"\xff", "invalid", "invalid_encoding"),
        ("not HLS", "invalid", "invalid_manifest"),
        ((404, {}, b"missing"), "error", "fetch_error"),
    ],
)
def test_root_failure_is_visible_without_metadata(http_server, text, status, reason):
    http_server.routes["/root"] = text
    report = analyze_playlist(http_server.url + "/root", http_retries=0)
    assert report["playlist"] is None
    resource = report["resources"][0]
    assert resource["status"] == status
    assert resource["reason"] == reason
    assert (resource["effective_url"] is not None) == (status == "invalid")


@pytest.mark.parametrize(
    ("tags", "uri", "payload", "status", "reason", "fetched"),
    [
        ("", "sample", b"unknown", "unsupported", "unknown_container", True),
        ('#EXT-X-KEY:METHOD=AES-128,URI="key"\n', "sample", b"", "skipped", "encrypted", False),
        ('#EXT-X-MAP:URI="init"\n', "sample", b"", "skipped", "initialization_dependent", False),
        ("#EXT-X-BYTERANGE:bad\n", "sample", b"", "invalid", "invalid_byterange", False),
        ("", "http://[bad?secret=hidden#fragment", b"", "invalid", "invalid_uri", False),
    ],
)
def test_samples_distinguish_unfetched_and_unsupported_resources(
    http_server, tags, uri, payload, status, reason, fetched
):
    http_server.routes["/root"] = media(uri, tags=tags)
    http_server.routes["/sample"] = payload
    report = analyze_playlist(http_server.url + "/root", 1, http_retries=0)
    resource = report["resources"][1]
    assert resource["status"] == status
    assert resource["reason"] == reason
    assert (resource["effective_url"] is not None) == fetched
    assert len(http_server.seen) == (2 if fetched else 1)
    assert "hidden" not in json.dumps(report)
    assert report["summary"]["inspection_complete"] is False


def test_invalid_child_uri_and_nested_master_are_visible(http_server):
    http_server.routes["/root"] = master("http://[bad?secret=hidden", "nested")
    http_server.routes["/nested"] = master("unfetched")
    report = analyze_playlist(http_server.url + "/root")
    assert [r["status"] for r in report["resources"]] == ["validated", "invalid", "invalid"]
    assert [r["reason"] for r in report["resources"]] == [None, "invalid_uri", "nested_master"]
    assert report["resources"][1]["url"] == "<invalid location>"
    assert len(http_server.seen) == 2
    assert report["status"] == "failed"


def test_ranges_and_redirects_record_actual_fetched_locations(http_server, ts_bytes):
    http_server.routes["/root"] = (302, {"Location": "/final/index?secret=redirect"}, b"")
    http_server.routes["/final/index?secret=redirect"] = media(
        "sample?secret=first", "sample?secret=first", tags=f"#EXT-X-BYTERANGE:{len(ts_bytes)}@0\n"
    ).replace(
        "#EXTINF:1,\nsample?secret=first\n#EXT-X-ENDLIST",
        f"#EXT-X-BYTERANGE:{len(ts_bytes)}\n#EXTINF:1,\nsample?secret=first\n#EXT-X-ENDLIST",
    )

    def ranged(request, count):
        start = 0 if count == 1 else len(ts_bytes)
        return (
            206,
            {"Content-Range": f"bytes {start}-{start + len(ts_bytes) - 1}/{len(ts_bytes)*2}"},
            ts_bytes,
        )

    http_server.routes["/final/sample?secret=first"] = ranged
    report = analyze_playlist(http_server.url + "/root", 2, http_retries=0)
    resources = report["resources"]
    assert resources[0]["effective_url"] == http_server.url + "/final/index?REDACTED"
    assert [r["status"] for r in resources] == ["validated", "inspected", "inspected"]
    assert [r["byte_range"] for r in resources] == [
        None,
        {"offset": 0, "length": 376},
        {"offset": 376, "length": 376},
    ]
    assert resources[1]["effective_url"] == http_server.url + "/final/sample?REDACTED"
    assert resources[1]["duplicate_of"] is None
    assert resources[2]["duplicate_of"] is None


def test_cli_usage_error_has_empty_inventory(capsys):
    assert main(["--json"]) == 2
    assert json.loads(capsys.readouterr().out)["resources"] == []


def test_inventory_traverses_variants_then_iframes_then_renditions(http_server, ts_bytes):
    http_server.routes["/root"] = (
        '#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="audio",URI="audio"\n'
        '#EXT-X-I-FRAME-STREAM-INF:BANDWIDTH=1000,URI="iframe"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=1000,AUDIO="audio"\nvariant\n'
    )
    for name in ("variant", "iframe", "audio"):
        http_server.routes["/" + name] = media("sample")
    http_server.routes["/sample"] = (302, {"Location": "/final.ts?secret=hidden"}, b"")
    http_server.routes["/final.ts?secret=hidden"] = ts_bytes
    report = analyze_playlist(http_server.url + "/root", 1)
    assert [r["url"].removeprefix(http_server.url) for r in report["resources"]] == [
        "/root",
        "/variant",
        "/sample",
        "/iframe",
        "/sample",
        "/audio",
        "/sample",
    ]
    assert [r["parent_id"] for r in report["resources"]] == [None, 0, 1, 0, 3, 0, 5]
    for index in (2, 4, 6):
        assert report["resources"][index]["effective_url"] == http_server.url + "/final.ts?REDACTED"
    assert http_server.counts["/sample"] == 3


def test_budget_rejected_sample_is_visible_without_claiming_a_fetch(http_server):
    http_server.routes["/root"] = media("sample")
    report = analyze_playlist(http_server.url + "/root", 1, max_requests=1)
    assert report["resources"][1]["status"] == "error"
    assert report["resources"][1]["reason"] == "fetch_error"
    assert report["resources"][1]["effective_url"] is None
    assert http_server.counts["/sample"] == 0
    assert report["status"] == "error"
