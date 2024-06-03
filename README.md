# kafka-acl-operator
Acl operator and acl chart to manage acl of kafka topic in Confluent kafka platform.

# prerequisite
```
$ python3 -V
Python 3.11.5

$ pip show confluent-kafka
Name: confluent-kafka
Version: 2.4.0
Summary: Confluent's Python client for Apache Kafka
Home-page: https://github.com/confluentinc/confluent-kafka-python
Author: Confluent Inc
Author-email: support@confluent.io

$ pip show kubernetes
Name: kubernetes
Version: 29.0.0
Summary: Kubernetes python client
Home-page: https://github.com/kubernetes-client/python
Author: Kubernetes

```
# info
Both Namespaced and Cluster scoped kafka-acl-operator and CRDs are available here.

For `cluster` scoped acl operator, use image tag with suffix `'-cl'`

For `namespaced` scoped acl operator, use image tag with suffix `'-ns'`

For both `cluster and namespaced` scoped acl operator, use image tag without suffix `'-ns' or '-cl'`
