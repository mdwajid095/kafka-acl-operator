# kafka-acl-operator
Acl operator chart to manage acl of kafka topic in Confluent kafka platform.

# prerequisite for operator
One property file required to authenticate with kafka cluster. Example property (adm.properties) added in operator directory.
The path of the property file should pass as a environment varialble (ENV) with name 'ADM_PROPERTIES_PATH'

export ADM_PROPERTIES_PATH=/home/wajid/adm.properties
export NAMESPACE=wowsome
export REST_URL=http://kafka.wowsome.svc.cluster.local:8090
export CLUSTER_ID=QNCeE1QyS1yGuW6_Vb3VRwow

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
# note
We have two CRDs to manage ACLs either at namespace level or k8s cluster level. So, as per requirement apply only one CRD at a time in k8s cluster.