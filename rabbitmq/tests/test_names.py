"""Unit tests of the rabbitmq generator (docs/specs/rabbitmq.md); command in the spec's implementation inventory."""

from box import Box

from .. import inv, main


def render(**sections):
    inv["parameters"] = Box(namespace="messaging", generators={"rabbitmq": sections})
    return {key: obj.root.to_dict() for key, obj in main({}).root.items()}


def test_name_names_the_resource():
    out = render(
        rabbitmqcluster={"rabbitmq": {"name": "production"}},
        queue={"rabbitmq-orders": {"name": "orders", "cluster_reference": "production"}},
    )
    assert set(out) == {"messaging/production-rabbitmqcluster", "messaging/orders-queue"}
    assert out["messaging/production-rabbitmqcluster"]["metadata"]["name"] == "production"
    assert out["messaging/production-rabbitmqcluster"]["metadata"]["labels"] == {"name": "production"}
    assert out["messaging/orders-queue"]["spec"] == {"name": "orders", "rabbitmqClusterReference": {"name": "production"}}


def test_key_names_the_resource_without_name():
    out = render(rabbitmqcluster={"rabbitmq": {}}, queue={"orders": {"cluster_reference": "rabbitmq"}})
    assert set(out) == {"messaging/rabbitmq-rabbitmqcluster", "messaging/orders-queue"}
    assert out["messaging/orders-queue"]["spec"]["name"] == "orders"


def test_same_name_fails():
    try:
        render(rabbitmqcluster={"rabbitmq": {"name": "production"}, "production": {}})
    except ValueError as e:
        assert str(e) == "rabbitmq: rabbitmqcluster 'rabbitmq' and 'production' both render 'production' in namespace 'messaging'"
    else:
        raise AssertionError("two entries rendering one name compiled")
