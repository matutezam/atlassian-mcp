from mcp_atlassian import normalize_profile
from mcp_atlassian.servers import get_server_for_profile, main_mcp, progressive_mcp


def test_normalize_profile_defaults_to_direct():
    assert normalize_profile(None) == "direct"
    assert normalize_profile("direct") == "direct"


def test_normalize_profile_accepts_progressive():
    assert normalize_profile("progressive") == "progressive"
    assert normalize_profile("  PROGRESSIVE  ") == "progressive"


def test_get_server_for_profile_returns_expected_server():
    assert get_server_for_profile("direct") is main_mcp
    assert get_server_for_profile("progressive") is progressive_mcp