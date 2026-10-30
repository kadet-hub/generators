"""Unit tests of the kubernetes generator (docs/specs/kubernetes.md); command in the spec's implementation inventory."""

from box import Box

from .. import utils
from ..base import Container, Workload
from ..generators import _build_service_bundle, generate_chainsaw_asserts, generate_gateway
from ..webhooks import APIService, MutatingWebhookConfiguration, ValidatingWebhookConfiguration, _webhooks

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


def test_webhook_configuration_names():
    comp = component(
        webhooks=[OPERATOR_WEBHOOK],
        validating_webhooks=[OPERATOR_WEBHOOK],
        webhook_ca_injected=True,
        webhook_configuration_name="cnpg-mutating-webhook-configuration",
        validating_webhook_configuration_name="cnpg-validating-webhook-configuration",
    )
    mutating = MutatingWebhookConfiguration(name="web", component=comp).root.to_dict()
    validating = ValidatingWebhookConfiguration(name="web", component=comp).root.to_dict()
    assert mutating["metadata"]["name"] == "cnpg-mutating-webhook-configuration"
    assert validating["metadata"]["name"] == "cnpg-validating-webhook-configuration"


def test_webhook_configuration_default_names():
    comp = component(webhooks=[OPERATOR_WEBHOOK], validating_webhooks=[OPERATOR_WEBHOOK], webhook_ca_injected=True)
    assert MutatingWebhookConfiguration(name="web", component=comp).root.to_dict()["metadata"]["name"] == "demo-web"
    assert ValidatingWebhookConfiguration(name="web", component=comp).root.to_dict()["metadata"]["name"] == "demo-web"


def mounts(volume_mounts):
    return Container(name="web", container={"image": "x/web:1.0", "volume_mounts": volume_mounts}).root.to_dict()["volumeMounts"]


def test_volume_mounts_of_one_volume():
    assert mounts(
        {
            "html": {"volume": "main", "mount_path": "/var/www/html", "sub_path": "html"},
            "config": {"volume": "main", "mount_path": "/var/www/html/config", "sub_path": "config"},
        }
    ) == [
        {"name": "main", "mountPath": "/var/www/html", "subPath": "html"},
        {"name": "main", "mountPath": "/var/www/html/config", "subPath": "config"},
    ]


def test_volume_mount_named_by_key():
    assert mounts({"data": {"mount_path": "/data"}}) == [{"name": "data", "mountPath": "/data"}]


def chainsaw(components, output_type=None, workloads=None, resources=None):
    """generate_chainsaw_asserts over components, chainsaw.workloads and chainsaw.resources, as {output key: manifest}."""
    entry = {"input_params": {"function": "generate_chainsaw_asserts"}}
    if output_type:
        entry["output_type"] = output_type
    previous = utils.inventory
    utils.inventory = lambda: Box(parameters={
        "namespace": "demo", "components": components, "kapitan": {"compile": [{"output_type": "yml"}, entry]},
        "generators": {"kubernetes": {"chainsaw": {"workloads": workloads, "resources": resources}}},
    })
    try:
        return {key: value.to_dict() for key, value in generate_chainsaw_asserts({}).root.items()}
    finally:
        utils.inventory = previous


def test_chainsaw_test_per_namespace():  # K8S-12
    out = chainsaw({
        "web": component(),
        "db": component(type="statefulset", replicas=1),
        "backup": component(type="job", schedule="0 3 * * *"),
        "api": component(namespace="other"),
    })
    assert out["demo/chainsaw-test"] == {
        "apiVersion": "chainsaw.kyverno.io/v1alpha1",
        "kind": "Test",
        "metadata": {"name": "demo"},
        "spec": {"namespace": "demo", "steps": [
            {"use": {"template": "web-assert.yaml"}},
            {"use": {"template": "db-assert.yaml"}},
        ]},
    }
    assert out["other/chainsaw-test"]["spec"]["steps"] == [{"use": {"template": "api-assert.yaml"}}]
    assert "demo/backup-assert" not in out
    assert {k for k in out if k.endswith("-assert")} == {"demo/web-assert", "demo/db-assert", "other/api-assert"}


def test_chainsaw_test_uses_output_type():  # K8S-12
    out = chainsaw({"web": component()}, output_type="yml")
    assert out["demo/chainsaw-test"]["spec"]["steps"] == [{"use": {"template": "web-assert.yml"}}]


def test_no_chainsaw_test_for_cronjobs_only():  # K8S-12
    assert chainsaw({"backup": component(type="job", schedule="0 3 * * *")}) == {}


def test_chainsaw_workloads_rendered_elsewhere():  # K8S-13
    out = chainsaw({"web": component()}, workloads={
        "operator": {"kind": "Deployment", "namespace": "storage"},
        "mon": {"kind": "StatefulSet", "namespace": "storage"},
        "csi-node": {"kind": "DaemonSet", "namespace": "storage"},
        "setup": {"kind": "Job"},
    })
    operator = out["storage/operator-assert"]["spec"]["try"][0]["assert"]["resource"]
    assert operator["apiVersion"] == "apps/v1"
    assert operator["metadata"] == {"name": "operator", "namespace": "storage"}
    [rollout] = [k for k in operator if k.startswith("(")]
    assert "status.updatedReplicas" in rollout and "status.availableReplicas" in rollout and ">= spec.replicas" in rollout
    mon = out["storage/mon-assert"]["spec"]["try"][0]["assert"]["resource"]
    assert any("status.readyReplicas" in k for k in mon)
    assert "status" in out["storage/csi-node-assert"]["spec"]["try"][0]["assert"]["resource"]
    setup = out["demo/setup-assert"]["spec"]["try"][0]["assert"]["resource"]
    assert (setup["apiVersion"], setup["status"]) == ("batch/v1", {"(conditions[?type == 'Complete'])": [{"status": "True"}]})
    assert out["storage/chainsaw-test"]["spec"]["steps"] == [
        {"use": {"template": "operator-assert.yaml"}},
        {"use": {"template": "mon-assert.yaml"}},
        {"use": {"template": "csi-node-assert.yaml"}},
    ]
    assert out["demo/chainsaw-test"]["spec"]["steps"] == [
        {"use": {"template": "web-assert.yaml"}},
        {"use": {"template": "setup-assert.yaml"}},
    ]


def test_chainsaw_workload_kind_must_be_known():  # K8S-13
    for entry in ({"kind": "CronJob"}, {}):
        try:
            chainsaw({}, workloads={"x": entry})
        except Exception as e:
            assert "chainsaw.workloads.x" in str(e) and "Deployment" in str(e), str(e)
        else:
            raise AssertionError(f"{entry} rendered")


def test_chainsaw_workload_and_component_of_one_name_fail():  # K8S-13
    try:
        chainsaw({"web": component()}, workloads={"web": {"kind": "Deployment"}})
    except ValueError as e:
        assert "produced twice" in str(e), str(e)
    else:
        raise AssertionError("rendered")


CEPH_CLUSTER = {
    "api_version": "ceph.rook.io/v1",
    "kind": "CephCluster",
    "name": "rook-ceph",
    "namespace": "rook-ceph",
    "status": {"phase": "Ready", "ceph": {"health": "HEALTH_OK"}},
}


def test_chainsaw_resource_status_assert():  # K8S-14
    out = chainsaw({"web": component()}, workloads={"rook-ceph-operator": {"kind": "Deployment", "namespace": "rook-ceph"}},
                   resources={"ceph-cluster": CEPH_CLUSTER, "pool": {"api_version": "ceph.rook.io/v1", "kind": "CephBlockPool", "status": {"phase": "Ready"}}})
    assert out["rook-ceph/ceph-cluster-assert"] == {
        "apiVersion": "chainsaw.kyverno.io/v1alpha1",
        "kind": "StepTemplate",
        "metadata": {"name": "ceph-cluster"},
        "spec": {"try": [{"assert": {"resource": {
            "apiVersion": "ceph.rook.io/v1",
            "kind": "CephCluster",
            "metadata": {"name": "rook-ceph", "namespace": "rook-ceph"},
            "status": {"phase": "Ready", "ceph": {"health": "HEALTH_OK"}},
        }}}]},
    }
    pool = out["demo/pool-assert"]["spec"]["try"][0]["assert"]["resource"]
    assert pool["metadata"] == {"name": "pool", "namespace": "demo"}
    assert out["rook-ceph/chainsaw-test"]["spec"]["steps"] == [
        {"use": {"template": "rook-ceph-operator-assert.yaml"}},
        {"use": {"template": "ceph-cluster-assert.yaml"}},
    ]
    assert out["demo/chainsaw-test"]["spec"]["steps"][-1] == {"use": {"template": "pool-assert.yaml"}}


def test_chainsaw_resource_needs_kind_and_status():  # K8S-14
    for entry in ({"kind": "CephCluster", "status": {"phase": "Ready"}}, {**CEPH_CLUSTER, "status": None},
                  {**CEPH_CLUSTER, "status": "Ready"}):
        try:
            chainsaw({}, resources={"x": entry})
        except Exception as e:
            assert "chainsaw.resources.x" in str(e) and "status mapping" in str(e), str(e)
        else:
            raise AssertionError(f"{entry} rendered")


def test_no_chainsaw_keys_render_as_before():  # K8S-14
    assert chainsaw({"web": component()}) == chainsaw({"web": component()}, workloads={}, resources={})
