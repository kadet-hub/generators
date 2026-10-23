"""Unit tests of the kubernetes generator (docs/specs/kubernetes.md); command in the spec's implementation inventory."""

from box import Box

from .. import utils
from ..base import Container, Workload
from ..generators import _build_service_bundle
from ..webhooks import APIService

# The generator reads the target's inventory; these tests have none. The
# gate's import policy has no pytest, so there are no fixtures.
utils.inventory = lambda: Box(parameters={})


def component(**keys):
    return {
        "name": "web",
        "type": "deployment",
        "namespace": "demo",
        "image": "x/web:1.0",
        "ports": {"http": {"service_port": 80}},
        **keys,
    }


def services(comp):
    workload = Workload(name="web", component=comp).root
    return [s.to_dict() for s in _build_service_bundle("web", comp, workload)]


def test_empty_service_renders_service():
    [service] = services(component(service={}))
    assert service["kind"] == "Service"
    assert "type" not in service["spec"]
    assert service["spec"]["ports"][0]["port"] == 80


def test_missing_or_null_service_renders_none():
    assert services(component()) == []
    assert services(component(service=None)) == []


def args(value):
    return Container(name="web", container={"image": "x/web:1.0", "args": value}).root.to_dict().get("args")


def test_args_list():
    assert args(["--since", "24h"]) == ["--since", "24h"]


def test_args_mapping():
    value = {"v": "--v=4", "port": 8080, "leader": ["--leader-election-namespace", "kube-system"], "dropped": None}
    assert args(value) == ["--v=4", "8080", "--leader-election-namespace", "kube-system"]


def test_args_mapping_value_mapping_fails():
    try:
        args({"v": {"level": 4}})
    except ValueError as e:
        assert "web: args.v" in str(e), str(e)
    else:
        raise AssertionError("no ValueError")


def test_null_service_on_statefulset():
    workload = Workload(name="web", component=component(type="statefulset", service=None)).root
    assert workload.spec.serviceName == "web"


def test_empty_service_serves_api_service():
    comp = component(service={}, api_service={"group": "m.example.com", "version": "v1", "insecure_skip_tls_verify": True})
    workload = Workload(name="web", component=comp).root
    api = APIService(name="web", component=comp, workload=workload).root.to_dict()
    assert api["spec"]["service"] == {"name": "web", "namespace": "demo", "port": 80}
