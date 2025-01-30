import os
import time
import logging
import threading
import configparser
import requests as rq
import sys
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from confluent_kafka.admin import AdminClient, AclBinding, AclBindingFilter, AclOperation, AclPermissionType, ResourceType, ResourcePatternType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load Kubernetes configuration
try:
    config.load_incluster_config()  # inside pod
except config.config_exception.ConfigException:
    try:
        config.load_kube_config()  # outside pod
    except config.config_exception.ConfigException:
        raise RuntimeError("Could not load Kubernetes configuration")

# Initialize Kubernetes API client
api = client.CustomObjectsApi()

# Load properties from adm.properties file
config_parser = configparser.ConfigParser()
adm_properties_path = os.getenv('ADM_PROPERTIES_PATH')
config_parser.read(adm_properties_path)
#config_parser.read('adm.properties')
kafka_properties = config_parser['ACL_CONFIG']
namespace = os.getenv('NAMESPACE', "wowsome")
rest_url = os.getenv('REST_URL', "http://kafka.wowsome.svc.cluster.local:8090")
#cluster_id = os.getenv('CLUSTER_ID', "QNCeE1QyS1yGuW6_Vb3VRw")
url = f"{rest_url}/kafka/v3/clusters"
response = rq.get(url)
if response.status_code == 200:
    data = response.json()
    cluster_id = data['data'][0]['cluster_id']
    # print(f"Cluster ID: {cluster_id}")
else:
    logging.error(f"Failed to retrieve CLUSTER_ID. Status code: {response.status_code}")

# Kafka AdminClient configuration
kafka_admin_client = AdminClient({
    'bootstrap.servers': kafka_properties['bootstrap.servers'],
    'security.protocol': kafka_properties['security.protocol'],
    'ssl.ca.location': kafka_properties['ssl.ca.location'],
    'ssl.certificate.location': kafka_properties['ssl.certificate.location'],
    'ssl.key.location': kafka_properties['ssl.key.location'],
    #'ssl.key.password': 'mystorepassword',
    'ssl.key.password': kafka_properties['ssl.key.password']
})

def apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope):
    try:
        restype_enum = ResourceType[restype.upper()]
        operation_enum = AclOperation[operation.upper()]
        permission_type_enum = AclPermissionType[permission_type.upper()]
        pattern_type_enum = ResourcePatternType[resource_pattern_type.upper()]

        for name in name:
            acl_binding = AclBinding(
                restype_enum,
                name,
                pattern_type_enum,
                principal,
                '*',
                operation_enum,
                permission_type_enum
            )
            kafka_admin_client.create_acls([acl_binding])
            logging.info(f"Applied ACL: {principal} {permission_type} {operation} on {restype}:{name} with pattern {resource_pattern_type} in {scope}")
    except Exception as e:
        logging.error(f"Failed to apply ACL: {e}")

def delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope):
    try:
        restype_enum = ResourceType[restype.upper()]
        operation_enum = AclOperation[operation.upper()]
        permission_type_enum = AclPermissionType[permission_type.upper()]
        pattern_type_enum = ResourcePatternType[resource_pattern_type.upper()]

        for name in name:
            acl_binding_filter = AclBindingFilter(
                restype_enum,
                name,
                pattern_type_enum,
                principal,
                '*',
                operation_enum,
                permission_type_enum
            )
            kafka_admin_client.delete_acls([acl_binding_filter])
            logging.info(f"Deleted ACL: {principal} {permission_type} {operation} on {restype}:{name} with pattern {resource_pattern_type} in {scope}")
    except Exception as e:
        logging.error(f"Failed to delete ACL: {e}")

def list_kafka_acls(namespace=None):
    group = "emp.namespaced.com"
    version = "v1alpha1"
    plural = "kafkaacls"

    if namespace:
        kafka_acls = api.list_namespaced_custom_object(group, version, namespace, plural)
    else:
        kafka_acls = api.list_cluster_custom_object(group, version, plural)

    if not kafka_acls.get('items'):
        logging.warning(f"No KafkaACLs: {kafka_acls.get('items')}")

    return kafka_acls
# way to call list_kafka_acls
# kafka_acls = list_kafka_acls(namespace)
# for acl in kafka_acls.get('items', []):
#     if acl['metadata']['name'] == "my-kafka-acl-ns-v1":
#         acl_list=acl['spec']['resourceName']
#         print(acl)

def get_kafka_acl(namespace=None, acl_name=None):
    group = "emp.namespaced.com"
    version = "v1alpha1"
    plural = "kafkaacls"
    name = acl_name
    
    try:
        if namespace:
            kafka_acl = api.get_namespaced_custom_object(group, version, namespace, plural, name)
            cr_resource_names = kafka_acl['spec']['resourceName']
        else:
            kafka_acl = api.list_cluster_custom_object(group, version, plural, name)
            cr_resource_names = kafka_acl['spec']['resourceName']
        return cr_resource_names

    except client.rest.ApiException as e:
        if e.status == 404:
            logging.error(f"KafkaACL {name} not found in namespace {namespace}")
        else:
            logging.error(f"Error retrieving KafkaACL: {e}")
# get_kafka_acl(namespace, "my-kafka-acl-ns-v1")

def ns_kafka_acl(principal, operation):
    URL = f"{rest_url}/kafka/v3/clusters/{cluster_id}/acls"
    try:
        response = rq.get(url=URL)
        response.raise_for_status()
    except rq.exceptions.RequestException as e:
        logging.error(f"OPERATOR COULD NOT FETCH ACLs from NAMESPACE. EXITING... Error: {e}")
        sys.exit(1)

    data = response.json().get("data", [])
    if not data:
        logging.info("No data found in the response.")
        sys.exit(1)

    ns_resource_names = [acl.get("resource_name") for acl in data if acl.get("principal") == principal and acl.get("operation") == operation]
    return ns_resource_names

def process_event(event, scope):
    event_type = event['type']
    kafka_acl = event['object']
    acl_name = kafka_acl['metadata']['name']
    spec = kafka_acl['spec']
    # print(spec)

    try:
        principal = spec['principal']
        restype = spec['resourceType']
        name = spec['resourceName']
        operation = spec['operation']
        permission_type = spec['permissionType']
        resource_pattern_type = spec['patternType']
    except KeyError as e:
        logging.error(f"KeyError: {e}")
        return

    if event_type == 'ADDED':
        apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)
    elif event_type == 'MODIFIED':
        cr_resource_names = get_kafka_acl(namespace, acl_name)
        ns_resource_names = ns_kafka_acl(principal, operation)
        cr_diff = [item for item in cr_resource_names if item not in ns_resource_names]
        ns_diff = [item for item in ns_resource_names if item not in cr_resource_names]
        # print(cr_diff, ns_diff)
        if cr_diff:
            name=cr_diff
            apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)
        if ns_diff:
            name=ns_diff
            delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)
    elif event_type == 'DELETED':
        delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)

def watch_cluster():
    resource_version = ''
    while True:
        try:
            stream = watch.Watch().stream(api.list_cluster_custom_object,
                                          group="emp.cluster.com",
                                          version="v1alpha1",
                                          plural="kafkaacls",
                                          resource_version=resource_version)
            for event in stream:
                process_event(event, "Cluster level")
        except Exception as e:
            logging.error(f"Error in cluster watch loop: {e}")
        time.sleep(1)

def watch_namespace():
    resource_version = ''
    while True:
        try:
            stream = watch.Watch().stream(api.list_namespaced_custom_object,
                                          group="emp.namespaced.com",
                                          version="v1alpha1",
                                          namespace=os.getenv('NAMESPACE'),
                                          plural="kafkaacls",
                                          resource_version=resource_version)
            for event in stream:
                process_event(event, os.getenv('NAMESPACE'))
        except Exception as e:
            logging.error(f"Error in namespace watch loop: {e}")
        time.sleep(1)

def main():
    # Create threads
    cluster_thread = threading.Thread(target=watch_cluster)
    namespace_thread = threading.Thread(target=watch_namespace)

    # Start threads
    cluster_thread.start()
    namespace_thread.start()

    # Wait for both threads to complete
    cluster_thread.join()
    namespace_thread.join()

if __name__ == "__main__":
    main()
