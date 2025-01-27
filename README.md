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
File `kafka_acl_operator.py` is the acl operator which handle list of array of topics per acl CR. e,g. `acl-ns.yaml`
This operator auto handle the acls in kafka cluster after addition or removal of topic in acls CR.

# docker
Image is also available for acl operator with below naming convention.
Docker image: `docker pull mdwajid095/kafka-acl-operator:v1`
