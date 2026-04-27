"""Tests for pebbles.scout.filters."""

from pebbles.scout.candidate import Candidate
from pebbles.scout.filters import CompositeFilter, PassThroughFilter


def make_candidate():
    return Candidate(
        principal_id="harbor",
        cluster_id="maritime_tech",
        source="rss",
        platform="rss",
        target_ref="https://example.com/x",
        target_content="anything",
    )


def test_pass_through_keeps_everything():
    f = PassThroughFilter()
    keep, reason = f.keep(make_candidate())
    assert keep is True
    assert reason == ""


def test_composite_short_circuits_on_first_drop():
    class DropAll:
        def __init__(self, name):
            self.name = name

        def keep(self, candidate):
            return (False, f"dropped by {self.name}")

    class KeepAll:
        def keep(self, candidate):
            return (True, "")

    composite = CompositeFilter([DropAll("first"), DropAll("second"), KeepAll()])
    keep, reason = composite.keep(make_candidate())
    assert keep is False
    assert "first" in reason
    assert "second" not in reason  # short-circuit


def test_composite_passes_when_all_keep():
    composite = CompositeFilter([PassThroughFilter(), PassThroughFilter()])
    keep, reason = composite.keep(make_candidate())
    assert keep is True
