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
Environment variables (defaults in parentheses):
```
  ADM_PROPERTIES_PATH       (required) path to .properties with [ACL_CONFIG]
  NAMESPACE                 ('confluent') K8s namespace to watch
  K8S_GROUP                 ('emp.namespaced.com')
  K8S_VERSION               ('v1alpha1')
  K8S_PLURAL                ('kafkaacls')
  AUTHORITATIVE             ('true') delete extras on reconcile
  COLLAPSE_TO_ALL           ('true') ALL supersedes granular ops
  FULL_RECONCILE_INTERVAL_SECONDS ('0') 0 disables periodic sweep
  LOG_LEVEL                 ('INFO') DEBUG|INFO|WARN|ERROR
  LOG_FORMAT                ('JSON') JSON|TEXT
  WATCH_TIMEOUT_SECONDS     ('300') long poll timeout
  MAX_ACL_BATCH_SIZE        ('100') max ACLs per AdminClient call
  MAX_RETRIES               ('5') max retries for Admin operations
  BACKOFF_BASE_SECONDS      ('0.5') initial backoff
  BACKOFF_MAX_SECONDS       ('8') cap for backoff
  JITTER_SECONDS            ('0.2') random jitter added to backoff sleeps
  DRY_RUN                   ('false') if true, only logs actions (no writes)
```

## docker
Image is also available for acl operator with below naming convention.

Docker image for namespaced scoped: `docker pull mdwajid095/kafka-acl-operator:v1-final`

