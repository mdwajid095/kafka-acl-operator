# kafka-acl-operator

## Overview

The Kafka ACL Operator is designed to manage Kafka Access Control Lists (ACLs) using Kubernetes Custom Resources. It watches for changes in Kubernetes custom resources and applies the corresponding ACLs to the Kafka cluster.

## prerequisite for operator
One property file required to authenticate with kafka cluster. Example property (adm.properties) added in operator directory.
The path of the property file should pass as a environment varialble (ENV) with name 'ADM_PROPERTIES_PATH'
```
export ADM_PROPERTIES_PATH=/home/wajid/adm.properties
export NAMESPACE=wowsome
```

## unit-testing
Below is the command to do the unit testing for kafka_acl_operator

`python3 -m unittest test_kafka_acl_operator.py`

## info
Any files or resources with the prefix or suffix `ns` indicate they are namespaced scoped, while those with `cl` indicate they are cluster scoped.

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

Docker image for namespaced scoped: `docker pull mdwajid095/kafka-acl-operator/ns:v1`

Docker image for cluster scoped: `docker pull mdwajid095/kafka-acl-operator/cl:v1`

