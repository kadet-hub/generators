"""Unit tests of the strimzi generator (docs/specs/strimzi.md); command in the spec's implementation inventory."""

from box import Box

from .. import inv, main

POOL = {"roles": ["controller", "broker"], "storage": "10Gi"}


def render(**sections):
    inv["parameters"] = Box(namespace="kafka", generators={"strimzi": sections})
    return {key: obj.root.to_dict() for key, obj in main({}).root.items()}


def test_name_names_the_resource():
    out = render(
        kafkas={"kafka": {"name": "events", "node_pools": {"kafka-dual": {"name": "dual", **POOL}}}},
        topics={"kafka-orders": {"name": "orders"}, "Payments_EU": {}},
        users={"kafka-orders-app": {"name": "orders-app", "cluster": "events"}},
    )
    assert set(out) == {
        "kafka/events-kafka",
        "kafka/events-dual-kafkanodepool",
        "kafka/orders-kafkatopic",
        "kafka/payments-eu-e1ed1a98-kafkatopic",
        "kafka/orders-app-kafkauser",
    }
    assert out["kafka/events-kafka"]["metadata"]["name"] == "events"
    for key, name in (("events-dual-kafkanodepool", "dual"), ("orders-kafkatopic", "orders"),
                      ("orders-app-kafkauser", "orders-app")):
        assert out[f"kafka/{key}"]["metadata"]["name"] == name
        assert out[f"kafka/{key}"]["metadata"]["labels"] == {"strimzi.io/cluster": "events"}
    assert "topicName" not in out["kafka/orders-kafkatopic"]["spec"]


def test_key_names_the_resource_without_name():
    out = render(kafkas={"kafka": {"node_pools": {"kafka-dual": POOL}}}, topics={"orders": {}})
    assert set(out) == {"kafka/kafka-kafka", "kafka/kafka-kafka-dual-kafkanodepool", "kafka/orders-kafkatopic"}
    assert out["kafka/orders-kafkatopic"]["metadata"]["labels"] == {"strimzi.io/cluster": "kafka"}


def test_cluster_names_the_kafka_not_its_key():
    try:
        render(kafkas={"kafka": {"name": "events"}, "other": {}}, topics={"orders": {"cluster": "kafka"}})
    except ValueError as e:
        assert str(e) == "KafkaTopic 'orders': cluster 'kafka' is not one of the Kafkas ['events', 'other']"
    else:
        raise AssertionError("a topic named a Kafka by its key")


def test_cluster_in_two_namespaces_fails():
    try:
        render(kafkas={"a": {"name": "events", "namespace": "a"}, "b": {"name": "events", "namespace": "b"}},
               cluster="events", topics={"orders": {}})
    except ValueError as e:
        assert str(e) == "KafkaTopic 'orders': Kafka 'events' is in the namespaces ['a', 'b'], set namespace"
    else:
        raise AssertionError("a topic of a Kafka in two namespaces compiled")
