import pytest
from agents.coordinator import Coordinator


@pytest.mark.tier3
class TestCrashRecovery:
    def test_coordinator_crash_mid_cycle(self, monkeypatch):
        coord = Coordinator(None, None, None, None, None)
        call_count = 0

        def crash_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated crash")
            return {"action": "noop"}

        monkeypatch.setattr(coord, "_review_external_submissions", crash_once)
        result = coord.act({})
        assert result["action"] == "noop"


@pytest.mark.tier3
class TestRapidCycles:
    def test_rapid_cycles_no_exhaustion(self, monkeypatch):
        coord = Coordinator(None, None, None, None, None)
        monkeypatch.setattr(coord, "_review_external_submissions", lambda: {"action": "noop"})
        monkeypatch.setattr(coord, "_improve_low_quality", lambda: [])
        for _ in range(10):
            result = coord.act({})
            assert result is not None


@pytest.mark.tier3
class TestInfoboxFailure:
    def test_infobox_generation_failure(self, monkeypatch):
        from agents.coordinator import Coordinator
        coord = Coordinator(None, None, None, None, None)
        monkeypatch.setattr(coord, "_generate_infobox", lambda t, c, ct: None)
        result = coord._build_article("Test", "science", "Some content here", "test")
        assert result is not None
        assert len(result) > 0


@pytest.mark.tier3
class TestEmptyDB:
    def test_empty_database_handling(self, monkeypatch):
        coord = Coordinator(None, None, None, None, None)
        monkeypatch.setattr("core.database.get_all_articles", lambda: [])
        result = coord._improve_low_quality()
        assert result == []
