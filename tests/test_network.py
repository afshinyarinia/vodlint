import time

import pytest

from vodlint.network import HttpClient


def test_shared_client_reads_local_paths_and_file_uris(tmp_path):
    path = tmp_path / "media with spaces.ts"
    path.write_bytes(b"0123456789")
    with HttpClient() as client:
        assert client.get_bytes(str(path)) == b"0123456789"
        assert client.fetch(path.as_uri(), byte_range=(2, 4)).data == b"2345"


def test_retry_applies_to_manifest_requests(http_server):
    http_server.routes["/media.m3u8"] = lambda request, count: (
        (503, {}, b"retry") if count == 1 else b"#EXTM3U\n"
    )
    with HttpClient(retries=1) as client:
        assert client.get_bytes(http_server.url + "/media.m3u8") == b"#EXTM3U\n"
    assert http_server.counts["/media.m3u8"] == 2


def test_retry_limit_is_enforced(http_server):
    http_server.routes["/media.m3u8"] = (503, {}, b"retry")
    with HttpClient(retries=1) as client, pytest.raises(OSError):
        client.get_bytes(http_server.url + "/media.m3u8")
    assert http_server.counts["/media.m3u8"] == 2


def test_timeout_is_enforced(http_server):
    def slow(request, count):
        time.sleep(0.15)
        return b"late"

    http_server.routes["/slow"] = slow
    with HttpClient(timeout_seconds=0.02, retries=0) as client, pytest.raises(OSError):
        client.get_bytes(http_server.url + "/slow")


def test_redirect_retains_effective_base_uri(http_server):
    http_server.routes["/old"] = (302, {"Location": "/new/index.m3u8"}, b"")
    http_server.routes["/new/index.m3u8"] = b"#EXTM3U\n"
    with HttpClient() as client:
        resource = client.fetch(http_server.url + "/old")
    assert resource.location == http_server.url + "/new/index.m3u8"
    assert resource.data == b"#EXTM3U\n"


def test_http_range_returns_only_requested_bytes(http_server):
    http_server.routes["/all.ts"] = (206, {"Content-Range": "bytes 3-6/10"}, b"3456")
    with HttpClient() as client:
        assert client.fetch(http_server.url + "/all.ts", byte_range=(3, 4)).data == b"3456"
    assert http_server.seen[0][1]["Range"] == "bytes=3-6"


@pytest.mark.parametrize(
    "response",
    [
        (200, {}, b"0123456789"),
        (206, {"Content-Range": "bytes 0-3/10"}, b"0123"),
        (206, {"Content-Range": "bytes 3-6/10"}, b"34"),
        (206, {}, b"3456"),
    ],
)
def test_ignored_wrong_and_truncated_ranges_fail(http_server, response):
    http_server.routes["/all.ts"] = response
    with HttpClient() as client, pytest.raises(OSError, match="[Rr]ange"):
        client.fetch(http_server.url + "/all.ts", byte_range=(3, 4))


@pytest.mark.parametrize("remote", [False, True])
def test_resource_size_limit_is_enforced(tmp_path, http_server, remote):
    path = tmp_path / "large"
    path.write_bytes(b"x" * 20)
    http_server.routes["/large"] = b"x" * 20
    location = http_server.url + "/large" if remote else str(path)
    with HttpClient(max_resource_bytes=10) as client, pytest.raises(OSError, match="limit"):
        client.get_bytes(location)


def test_stream_without_content_length_is_bounded(http_server):
    http_server.routes["/large"] = (200, {"Content-Length": ""}, b"x" * 200)
    with HttpClient(max_resource_bytes=10) as client, pytest.raises(OSError, match="limit"):
        client.get_bytes(http_server.url + "/large")


def test_total_budget_and_request_limit_are_enforced(tmp_path):
    path = tmp_path / "small"
    path.write_bytes(b"abc")
    with HttpClient(max_total_bytes=5) as client:
        assert client.get_bytes(str(path)) == b"abc"
        with pytest.raises(OSError, match="limit"):
            client.get_bytes(str(path))
    with HttpClient(max_requests=1) as client:
        client.get_bytes(str(path))
        with pytest.raises(OSError, match="limit"):
            client.get_bytes(str(path))


def test_short_local_range_is_an_error(tmp_path):
    path = tmp_path / "short"
    path.write_bytes(b"abc")
    with HttpClient() as client, pytest.raises(OSError, match="[Rr]ange"):
        client.fetch(str(path), byte_range=(2, 4))


@pytest.mark.parametrize("status", [302, 503])
def test_redirect_and_retry_bodies_cannot_bypass_byte_limits(http_server, status):
    def intermediate(request, count):
        if status == 302:
            return (302, {"Location": "/final"}, b"x" * 100000)
        return (503, {}, b"x" * 100000) if count == 1 else b"#EXTM3U\n"

    http_server.routes["/start"] = intermediate
    http_server.routes["/final"] = b"#EXTM3U\n"
    with HttpClient(max_resource_bytes=100, max_total_bytes=100, retries=1) as client:
        try:
            client.fetch(http_server.url + "/start")
        except OSError as error:
            assert "limit" in str(error)
        else:
            pytest.fail("Oversize intermediate response must be rejected before following/retrying")


def test_unrequested_partial_response_fails(http_server):
    http_server.routes["/partial"] = (206, {"Content-Range": "bytes 0-7/100"}, b"#EXTM3U\n")
    with HttpClient() as client, pytest.raises(OSError, match="[Pp]artial|[Rr]ange"):
        client.fetch(http_server.url + "/partial")


def test_malformed_resource_url_becomes_resource_error():
    with HttpClient() as client, pytest.raises(OSError):
        client.fetch("http://[bad")


@pytest.mark.parametrize("status", [302, 503])
def test_intermediate_bodies_count_toward_combined_budget(http_server, status):
    http_server.routes["/start"] = lambda request, count: (
        (302, {"Location": "/final"}, b"abc")
        if status == 302
        else (503, {}, b"abc") if count == 1 else b"12345678"
    )
    http_server.routes["/final"] = b"12345678"
    with HttpClient(max_total_bytes=10, retries=1) as client, pytest.raises(OSError, match="limit"):
        client.fetch(http_server.url + "/start")


def test_redirect_loop_is_bounded(http_server):
    http_server.routes["/loop"] = (302, {"Location": "/loop"}, b"")
    with HttpClient() as client, pytest.raises(OSError, match="redirect limit"):
        client.fetch(http_server.url + "/loop")
    assert http_server.counts["/loop"] == 31


def test_redirect_preserves_cookie_jar(http_server):
    http_server.routes["/start"] = (
        302,
        {"Location": "/final", "Set-Cookie": "session=ok; Path=/"},
        b"",
    )
    http_server.routes["/final"] = lambda request, count: (
        b"ok" if request.headers.get("Cookie") == "session=ok" else (403, {}, b"denied")
    )
    with HttpClient() as client:
        assert client.get_bytes(http_server.url + "/start") == b"ok"


def test_cross_host_redirect_strips_explicit_credentials(http_server):
    other_host = http_server.url.replace("127.0.0.1", "localhost")
    http_server.routes["/start"] = (302, {"Location": other_host + "/final"}, b"")
    http_server.routes["/final"] = b"ok"
    with HttpClient() as client:
        assert (
            client.get_bytes(
                http_server.url + "/start",
                headers={"authorization": "Bearer secret", "cookie": "x=y"},
            )
            == b"ok"
        )
    assert "Authorization" not in http_server.seen[-1][1]
    assert "Cookie" not in http_server.seen[-1][1]
