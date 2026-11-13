"""Unit tests of match_kinds on the policies.kyverno.io kinds (README, table of shorthands).

Run from the repository root with `PYTHONDONTWRITEBYTECODE=1 uv run -p 3.12 --with pytest
--with 'kapitan==0.36.3' --with 'omegaconf==2.4.0.dev4' python3 -m pytest -q -p no:cacheprovider
kyverno/tests` (bytecode in the tree fails SEC-5).
"""

from .. import _resource_rules


def test_deployment():
    assert _resource_rules(["Deployment"], ("CREATE", "UPDATE")) == [
        {"apiGroups": ["apps"], "apiVersions": ["v1"], "operations": ["CREATE", "UPDATE"], "resources": ["deployments"]}
    ]


def test_pod_is_in_the_core_group():
    assert _resource_rules(["Pod"], ("CREATE",)) == [
        {"apiGroups": [""], "apiVersions": ["v1"], "operations": ["CREATE"], "resources": ["pods"]}
    ]


def test_event_is_served_by_two_groups():
    assert _resource_rules(["Event"], ("CREATE",)) == [
        {"apiGroups": ["", "events.k8s.io"], "apiVersions": ["v1"], "operations": ["CREATE"], "resources": ["events"]}
    ]


def test_crd_kind_fails():
    try:
        _resource_rules(["Certificate"], ("CREATE",))
    except ValueError as e:
        assert "'Certificate'" in str(e), e
    else:
        raise AssertionError("match_kinds accepted the CRD kind Certificate")
