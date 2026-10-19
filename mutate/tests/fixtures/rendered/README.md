`podinfo/` is the output of the podinfo Helm chart 6.15.0
(https://github.com/stefanprodan/podinfo, Apache-2.0, chart from
https://stefanprodan.github.io/podinfo), unchanged, rendered with Helm 3.17.0:

    helm template podinfo podinfo --namespace apps --set hpa.enabled=true \
      --set redis.enabled=true --set tests.enable=true --output-dir .

The fixture copies it with a `copy` entry, where a project would use the
`helm` input, which writes the same files one directory deeper (`podinfo/templates/`).
