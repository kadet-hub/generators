"""Generators such as rabbitmq read the inventory when imported; their unit tests run with an empty target."""

from kapitan.inputs.kadet import current_target, inventory_global

inventory_global()["unit-test"] = {"parameters": {}}
current_target.set("unit-test")
