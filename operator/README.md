# kafka-acl-operator
Acl operator manage acl of kafka topic in Confluent kafka platform k8s CR ways.

# prerequisite for operator
One property file required to authenticate with kafka cluster. Example property (adm.properties) added here.
The path of the property file should pass as a environment varialble (ENV) with name 'ADM_PROPERTIES_PATH'

Like, 
`
export ADM_PROPERTIES_PATH=/home/wajid/adm.properties
export NAMESPACE=wowsome
export REST_URL=http://kafka.wowsome.svc.cluster.local:8090
export CLUSTER_ID=QNCeE1QyS1yGuW6_Vb3VRwow
`

# unit-testing
Below is the command to do the unit testing for kafka_acl_operator

`python3 -m unittest test_kafka_acl_operator.py`

# info

File `kafka_acl_operator.py` is the acl operator which handle list of array of topics per acl CR. e,g. `acl-ns.yaml`
This operator auto handle the acls in kafka cluster after addition or removal of topic in acls CR.

# docker
Image is also available for acl operator with below naming convention.
Docker image: `docker pull mdwajid095/kafka-acl-operator:v1`

