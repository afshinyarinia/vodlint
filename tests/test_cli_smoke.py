from hls_health.cli import build_parser


def test_build_parser_has_options():
	parser = build_parser()
	args = parser.parse_args(["https://example.com/playlist.m3u8", "-s", "0", "--json"])
	assert args.segments == 0
	assert args.json is True
