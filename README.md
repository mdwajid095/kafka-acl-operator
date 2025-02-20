# kafka-acl-operator

## Overview
The Kafka ACL Operator is designed to manage Kafka Access Control Lists (ACLs) using Kubernetes Custom Resources. It watches for changes in Kubernetes custom resources and applies the corresponding ACLs to the Kafka cluster.

## prerequisite
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
## feature
This operator supports all the feature supported by kafka. And we can pass array of resourceName and operation. See example in file `acl.yaml`.

## extra feature
This operator supports the following meta operations, which are combinations of multiple operations. The meta operations are defined as follows:
```
# meta operations
operation_mapping = {
    'CONSUMER': ['READ', 'DESCRIBE', 'DESCRIBE_CONFIGS'],
    'PRODUCER': ['WRITE', 'DESCRIBE', 'DESCRIBE_CONFIGS'],
    'PROSUMER': ['READ', 'WRITE', 'DESCRIBE', 'DESCRIBE_CONFIGS']
}
```

## docker
Image is also available for acl operator with below naming convention.

Docker image for namespaced scoped: `docker pull mdwajid095/kafka-acl-operator:v1`

## Conclusion

The Kafka ACL Operator simplifies the management of Kafka ACLs by leveraging Kubernetes custom resources. It ensures that the desired ACLs are applied to the Kafka cluster and keeps them in sync with the custom resources.
