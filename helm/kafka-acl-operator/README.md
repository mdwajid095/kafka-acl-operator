# kafka-acl-operator
Acl operator chart to manage acl of kafka topic in Confluent kafka platform.

# prerequisite for operator
One property file required to authenticate with kafka cluster. Example property (adm.properties) added in operator directory.
The path of the property file should pass as a environment varialble (ENV) with name 'ADM_PROPERTIES_PATH'

`ADM_PROPERTIES_PATH` and `NAMESPACE` can also be set in deployment opearator.

One k8s secret is also required with `adm.properties` and file configured in adm.properties. Below is the command to create k8s secret.
```
kubectl -n wowsome create secret generic acl-operator-secret \
--from-file=adm.properties=adm.properties \
--from-file=cacerts.pem=cacerts.pem \
--from-file=fullchain.pem=fullchain.pem \
--from-file=privkey.pem=privkey.pem \
--save-config --dry-run=client -o yaml | \
kubectl apply -f -
```

# info
File `ns-scoped-operator.py` only handle the namespaced scoped CDRs.
And `kafka-acl-operator.py` handle both namespaced and cluster scoped CRDs.
