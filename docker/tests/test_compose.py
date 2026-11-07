"""Unit tests of the Compose output (docs/specs/docker.md); command in the spec's implementation inventory."""

from pathlib import Path

import yaml
from box import Box

from .. import inventory_data, main

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "inventory" / "targets" / "compose.yml"
GOLDEN = HERE / "golden" / "compose.yml"


def render(parameters):
    inventory_data["parameters"] = Box(parameters)
    return dict(main({}).root)


def services(components, compose=None, **parameters):
    generators = parameters.pop("generators", {})
    generators["docker"] = {"compose": compose or {}}
    out = render({"components": components, "generators": generators, **parameters})
    return yaml.safe_load(out["compose.yml"])["services"]


def service(**component):
    return services({"app": {"image": "app:1", **component}})["app"]


def raises(message, call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except ValueError as e:
        assert message in str(e), str(e)
    else:
        raise AssertionError(f"no ValueError: {message}")


def fails(message, **component):
    raises(f"components.app: {message}", service, **component)


def fixture():
    return yaml.safe_load(FIXTURE.read_text())["parameters"]


def test_golden():
    out = render(fixture())
    assert set(out) == {"compose.yml"}
    assert out["compose.yml"] == GOLDEN.read_text()


def test_without_switch():
    parameters = fixture()
    parameters["generators"]["docker"] = {"dockerfiles": {"app": {"base_image": "alpine:3.24.2"}}}
    assert set(render(parameters)) == {"app/Dockerfile"}
    parameters["generators"]["docker"]["compose"] = None
    assert set(render(parameters)) == {"app/Dockerfile"}
    parameters["generators"]["docker"]["compose"] = True
    raises("generators.docker.compose must be a mapping or null", render, parameters)


def test_defaults():
    out = services(
        {
            "web": {"application": "shop", "image": "web:1", "env": {"A": "own"}},
            "db": {"type": "statefulset", "image": "db:1"},
        },
        applications={"shop": {"component_defaults": {"env": {"A": "app", "B": "app"}}}},
        generators={
            "manifest": {
                "default_config": {"env": {"B": "config", "C": "config"}},
                "resource_defaults": {"statefulset": {"read_only_root_filesystem": True}},
            }
        },
    )
    assert out["web"]["environment"] == {"A": "own", "B": "app", "C": "config"}
    assert out["db"]["read_only"] is True
    assert "read_only" not in out["web"]
    raises(
        "components.web: no Compose mapping for security_profile",
        services,
        {"web": {"image": "web:1"}},
        generators={"manifest": {"default_config": {"security_profile": "restricted"}}},
    )


def test_disabled():
    out = services({"on": {"image": "a:1", "enabled": True}, "off": {"image": "b:1", "enabled": False}})
    assert set(out) == {"on"}


def test_command_and_args():
    out = service(command=["/bin/app", "serve"], args={"port": ["--port", 8080], "debug": None, "level": "info"})
    assert out["entrypoint"] == ["/bin/app", "serve"]
    assert out["command"] == ["--port", "8080", "info"]
    assert service(args=["-v", 2])["command"] == ["-v", "2"]
    assert "command" not in service(args={"debug": None})
    fails("args.port must be a string or a list", args={"port": {"value": 1}})
    fails("command must be a list", command="/bin/app serve")


def test_user_and_read_only():
    assert service(security_context={"runAsUser": 1000})["user"] == "1000"
    out = service(security_context={"runAsUser": 1000, "runAsGroup": 2000}, read_only_root_filesystem=True)
    assert (out["user"], out["read_only"]) == ("1000:2000", True)
    assert "read_only" not in service(
        security_context={"readOnlyRootFilesystem": False}, read_only_root_filesystem=True
    )
    assert service(security_context={"readOnlyRootFilesystem": True})["read_only"] is True
    fails("no Compose mapping for security_context.runAsGroup without runAsUser", security_context={"runAsGroup": 1})


def test_dollar():
    out = service(
        env={"PRICE": "costs $5", "PASSWORD": {"secretKeyRef": {"key": "PASSWORD"}}},
        secrets={"s": {"string_data": {"PASSWORD": {"value": "a$(b)$$c"}}}},
        healthcheck={"readiness": {"type": "command", "command": ["sh", "-c", "test $HOME"]}},
    )
    assert out["environment"] == {"PRICE": "costs $$5", "PASSWORD": "a$$(b)$$$$c"}
    assert out["healthcheck"]["test"] == ["CMD", "sh", "-c", "test $$HOME"]
    message = "Kubernetes expands $( and $$ here and Compose does not"
    fails(f"env.URL: {message}", env={"URL": "redis://:$(PASSWORD)@valkey"})
    fails(f"args: {message}", args=["--price=$$5"])
    fails(f"command: {message}", command=["sh", "-c", "echo $(date)"])


def test_resources():
    out = service(
        resources={
            "limits": {"cpu": "1500m", "memory": "2Gi"},
            "requests": {"cpu": 2, "memory": "512Ki"},
        }
    )
    assert out["deploy"]["resources"] == {
        "limits": {"cpus": "1.5", "memory": "2g"},
        "reservations": {"cpus": "2", "memory": "512k"},
    }
    assert service(resources={"limits": {"cpu": "100m"}})["deploy"]["resources"] == {"limits": {"cpus": "0.1"}}
    assert "deploy" not in service(resources={})


def test_overrides():
    out = services(
        {"app": {"image": "app:1", "ports": {"http": {"container_port": 8080}}}},
        compose={
            "services": {
                "app": {"restart": None, "expose": ["9090"], "deploy": {"replicas": 1}},
                "proxy": {"image": "caddy:2"},
            }
        },
    )
    assert out["app"] == {"image": "app:1", "expose": ["9090"], "deploy": {"replicas": 1}}
    assert out["proxy"] == {"image": "caddy:2"}


def test_volumes():
    claim = {"data": {"spec": {"resources": {"requests": {"storage": "1Gi"}}}}}
    out = render(
        {
            "components": {
                "db": {
                    "image": "db:1",
                    "volume_claims": claim,
                    "volume_mounts": {"data": {"mount_path": "/data"}, "ro": {"volume": "data", "mount_path": "/ro", "read_only": True}},
                }
            },
            "generators": {"docker": {"compose": {}}},
        }
    )
    document = yaml.safe_load(out["compose.yml"])
    assert document["services"]["db"]["volumes"] == ["data:/data", "data:/ro:ro"]
    assert document["volumes"] == {"data": {}}
    raises(
        "components.b: volume_claims.data: components.a has a claim",
        services,
        {"a": {"image": "a:1", "volume_claims": claim}, "b": {"image": "b:1", "volume_claims": claim}},
    )


REFUSALS = [
    ({"security_profile": "restricted", "replicas": 1}, "no Compose mapping for replicas, security_profile"),
    ({"type": "job"}, "no Compose mapping for type job"),
    ({"enable_service_links": True}, "no Compose mapping for enable_service_links other than false"),
    ({"image": None}, "image is required"),
    ({"env": {"NODE": {"fieldRef": {"fieldPath": "spec.nodeName"}}}}, "no Compose mapping for env.NODE"),
    ({"env": {"X": {"secretKeyRef": {"key": "X", "name": "other"}}}}, "no Compose mapping for env.X"),
    ({"env": {"X": {"secretKeyRef": {"key": "X"}, "configMapKeyRef": {"key": "X"}}}}, "no Compose mapping for env.X"),
    ({"env": {"X": {"secretKeyRef": {"key": "X"}}}}, "env.X: no secrets entry has string_data.X"),
    ({"env": {"X": {"configMapKeyRef": {"key": "X"}}}}, "env.X: no config_maps entry has data.X"),
    ({"secrets": {"s": {"string_data": {}, "mount": "/s"}}}, "no Compose mapping for secrets.s.mount"),
    ({"secrets": {"s": {"data": {"X": {"value": "x"}}}}}, "no Compose mapping for secrets.s.data"),
    ({"config_maps": {"c": {"data": {"X": {"template": "x.j2"}}}}}, "no Compose mapping for config_maps.c.data.X other than value"),
    (
        {"healthcheck": {"readiness": {"type": "http", "port": "http", "path": "/"}}},
        "no Compose mapping for healthcheck.readiness type http: a Compose health check runs a command in the container; "
        "set it in generators.docker.compose.services.app.healthcheck",
    ),
    ({"healthcheck": {"liveness": {"type": "command", "command": ["true"]}}}, "no Compose mapping for healthcheck.liveness"),
    (
        {"healthcheck": {"readiness": {"type": "command", "command": ["true"], "success_threshold": 2}}},
        "no Compose mapping for healthcheck.readiness.success_threshold",
    ),
    ({"volume_mounts": {"tmp": {"mount_path": "/tmp"}}}, "no Compose mapping for volume_mounts.tmp: volume tmp is no volume_claims entry"),
    (
        {"volume_claims": {"data": {}}, "volume_mounts": {"data": {"mount_path": "/d", "sub_path": "x"}}},
        "no Compose mapping for volume_mounts.data.sub_path",
    ),
    ({"resources": {"limits": {"ephemeral-storage": "1Gi"}}}, "no Compose mapping for resources.limits.ephemeral-storage"),
    ({"resources": {"limits": {"memory": "1G"}}}, "no Compose mapping for resources.limits.memory 1G"),
    ({"resources": {"claims": [{"name": "gpu"}]}}, "no Compose mapping for resources.claims"),
    ({"security_context": {"allowPrivilegeEscalation": False}}, "no Compose mapping for security_context.allowPrivilegeEscalation"),
]


def test_refusals():
    for component, message in REFUSALS:
        fails(message, **component)


def test_probe_without_type_renders_nothing():
    assert "healthcheck" not in service(healthcheck={"liveness": {"path": "/"}, "readiness": {}})
