"""Unit tests of the kubernetes generator (docs/specs/kubernetes.md); command in the spec's implementation inventory."""

from box import Box

from .. import utils
from ..base import Container, Workload
from ..generators import _build_service_bundle, generate_gateway
from ..webhooks import APIService, _webhooks

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


def routes(settings, namespace="cloud"):
    """generate_gateway with generators.kubernetes set to settings, as {output key: manifest}."""
    previous = utils.inventory
    utils.inventory = lambda: Box(parameters={"namespace": namespace, "generators": {"kubernetes": settings}})
    try:
        return {key: value.root.to_dict() for key, value in generate_gateway({}).root.items()}
    finally:
        utils.inventory = previous


NEXTCLOUD_ROUTE = {
    "hostnames": ["cloud.example.com"],
    "parent_refs": [{"name": "gateway", "namespace": "gateway", "section_name": "https"}],
    "rules": {
        "caldav": {
            "matches": {"caldav": {"type": "Exact", "value": "/.well-known/caldav"}},
            "redirect": {"replace_full_path": "/remote.php/dav", "status_code": 301},
        },
        "app": {
            "matches": {"root": {"type": "PathPrefix", "value": "/"}},
            "name": "nextcloud",
            "port": 8080,
        },
    },
}


def test_route_parent_refs():
    out = routes({"routes": {"nextcloud": NEXTCLOUD_ROUTE}})
    assert list(out) == ["cloud/nextcloud-route"]
    route = out["cloud/nextcloud-route"]
    assert (route["kind"], route["metadata"]["namespace"]) == ("HTTPRoute", "cloud")
    assert route["spec"]["parentRefs"] == [{"name": "gateway", "namespace": "gateway", "sectionName": "https"}]
    assert route["spec"]["rules"][1]["backendRefs"] == [
        {"group": "", "kind": "Service", "name": "nextcloud", "port": 8080, "weight": 1}
    ]


def test_route_without_parent_fails():
    for parent_refs in (None, [], [{"namespace": "gateway"}]):
        try:
            routes({"routes": {"nextcloud": {**NEXTCLOUD_ROUTE, "parent_refs": parent_refs}}})
        except ValueError as e:
            assert "route 'nextcloud'" in str(e), str(e)
        else:
            raise AssertionError(f"no ValueError for parent_refs {parent_refs!r}")


def test_redirect_path():
    route = routes({"routes": {"nextcloud": NEXTCLOUD_ROUTE}})["cloud/nextcloud-route"]
    assert route["spec"]["rules"][0]["filters"] == [
        {
            "type": "RequestRedirect",
            "requestRedirect": {"statusCode": 301, "path": {"type": "ReplaceFullPath", "replaceFullPath": "/remote.php/dav"}},
        }
    ]
    gateway = {
        "listeners": {"http": {"port_number": 80, "protocol": "HTTP"}},
        "routes": {
            "strip": {
                "type": "http",
                "rules": {"api": {"matches": {"api": {"value": "/api"}}, "redirect": {"replace_prefix_match": ""}}},
            }
        },
    }
    route = routes({"gateways": {"public": gateway}})["cloud/strip-gw-routes"]
    assert route["spec"]["rules"][0]["filters"][0]["requestRedirect"] == {
        "path": {"type": "ReplacePrefixMatch", "replacePrefixMatch": ""}
    }


def test_redirect_both_paths_fails():
    rule = {"redirect": {"replace_full_path": "/a", "replace_prefix_match": "/b"}}
    try:
        routes({"routes": {"nextcloud": {**NEXTCLOUD_ROUTE, "rules": {"both": rule}}}})
    except ValueError as e:
        assert "not both" in str(e), str(e)
    else:
        raise AssertionError("no ValueError")


OPERATOR_WEBHOOK = {"name": "vcluster.cnpg.io", "clientConfig": {"service": {"name": "cnpg-webhook-service", "path": "/validate"}}}


def test_webhook_ca_injected():
    comp = component(validating_webhooks=[OPERATOR_WEBHOOK], webhook_ca_injected=True)
    _, [webhook] = _webhooks("web", comp, "validating_webhooks")
    assert "caBundle" not in webhook["clientConfig"]
    assert webhook.get("failurePolicy", "Fail") == "Fail"


def test_webhook_without_ca_fails():
    try:
        _webhooks("web", component(validating_webhooks=[OPERATOR_WEBHOOK]), "validating_webhooks")
    except ValueError as e:
        assert "webhook_ca_injected" in str(e), str(e)
    else:
        raise AssertionError("no ValueError")
