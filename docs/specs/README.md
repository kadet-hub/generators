# Specs

One spec per area in `docs/specs/<area>.md`, in the format of the registry's
[specs](https://github.com/kadet-hub/registry/tree/main/docs/specs): header
with status, governed code and verified commit, then problem and decisions,
subject sections with requirements, open questions and the implementation
inventory last. Requirements carry an area prefix, are never renumbered and
name their check (`Test:`) and origin (`Since:`). A change to code,
configuration or CI starts by editing the spec it touches, in the same pull
request, as its first commit.

| Spec | Area |
|---|---|
| [check.md](check.md) | Gate check (`CHK-`) |
| [upstream.md](upstream.md) | Upstream schema updates (`UPD-`) |
| [mutate.md](mutate.md) | mutate generator (`MUT-`) |
| [kubevirt.md](kubevirt.md) | kubevirt generator (`KV-`) |
| [kubernetes.md](kubernetes.md) | kubernetes generator (`K8S-`) |
| [cloudnative-pg.md](cloudnative-pg.md) | cloudnative-pg generator (`CNPG-`) |
| [rabbitmq.md](rabbitmq.md) | rabbitmq generator (`RMQ-`) |
| [strimzi.md](strimzi.md) | strimzi generator (`STZ-`) |
