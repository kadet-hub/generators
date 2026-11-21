"""Unit tests of the legacy kyverno.io sections (README, Kyverno 1.20; UPD-13 of docs/specs/upstream.md)."""

from .. import _LEGACY_SECTIONS, main


def render(monkeypatch, kyverno):
    inventory = type("Inventory", (), {"parameters": {"generators": {"kyverno": kyverno}}})
    monkeypatch.setattr(f"{main.__module__}.inv", inventory)
    return main({})


def test_legacy_sections_fail(monkeypatch):
    for section in _LEGACY_SECTIONS:
        try:
            render(monkeypatch, {section: {"p": {}}})
        except ValueError as e:
            assert f"generators.kyverno.{section}: Kyverno 1.20 rejects" in str(e), e
        else:
            raise AssertionError(f"{section} rendered without an error")


def test_empty_legacy_section_renders_nothing(monkeypatch):
    assert render(monkeypatch, {"cluster_policies": {}}).root == {}
