# kafka-acl-operator
Acl operator and acl chart to manage acl of kafka topic in Confluent kafka platform.

# prerequisite for operator
One property file required to authenticate with kafka cluster. Example property (adm.properties) added here.
The path of the property file should pass as a environment varialble (ENV) with name 'ADM_PROPERTIES_PATH'

Like, 
`
export ADM_PROPERTIES_PATH=/home/wajid/adm.properties
export NAMESPACE=wowsome
`

# info
File `ns-scoped-operator.py` only handle the namespaced scoped CDRs.
And `kafka-acl-operator.py` handle both namespaced and cluster scoped CRDs.
