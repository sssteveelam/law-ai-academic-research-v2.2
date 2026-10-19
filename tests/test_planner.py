from pathlib import Path

from services.search.planner import ResearchProfile


def test_profile_builds_editable_query() -> None:
    profile = ResearchProfile.from_file(Path("config/research_profile.json"))
    query = profile.build_query()
    assert '"explaining AI"' in query
    assert "fault" in query
    assert " OR " in query
