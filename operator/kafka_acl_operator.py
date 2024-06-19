import os
import time
import logging
import threading
import configparser
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
        # Convert input parameters to Kafka ACL objects
        restype_enum = ResourceType[restype.upper()]
        operation_enum = AclOperation[operation.upper()]
        permission_type_enum = AclPermissionType[permission_type.upper()]
        pattern_type_enum = ResourcePatternType[resource_pattern_type.upper()]

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
        # Convert input parameters to Kafka ACL filter objects
        restype_enum = ResourceType[restype.upper()]
        operation_enum = AclOperation[operation.upper()]
        permission_type_enum = AclPermissionType[permission_type.upper()]
        pattern_type_enum = ResourcePatternType[resource_pattern_type.upper()]

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

def process_event(event, scope):
    event_type = event['type']
    kafka_acl = event['object']
    resource_version = kafka_acl['metadata']['resourceVersion']
    spec = kafka_acl['spec']

    principal = spec['principal']
    restype = spec['resourceType']
    name = spec['resourceName']
    operation = spec['operation']
    permission_type = spec['permissionType']
    resource_pattern_type = spec['patternType']

    if event_type == 'ADDED' or event_type == 'MODIFIED':
        apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)
    elif event_type == 'DELETED':
        delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)

def watch_cluster():
    resource_version = ''
    while True:
        try:
            stream = watch.Watch().stream(api.list_cluster_custom_object,
                                      group="kafka.cluster.com",
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
                                      group="kafka.namespaced.com",
                                      version="v1alpha1",
                                      namespace= os.getenv('NAMESPACE'),
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

