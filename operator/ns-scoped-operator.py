import os
import time
import logging
import configparser
from kubernetes import client, config, watch
from confluent_kafka.admin import AdminClient, AclBinding, AclBindingFilter, AclOperation, AclPermissionType, ResourceType, ResourcePatternType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load Kubernetes configuration
try:
    config.load_incluster_config()  # Try to load the in-cluster config
except config.config_exception.ConfigException:
    try:
        config.load_kube_config()  # If the in-cluster config can't be loaded, try the kubeconfig
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
    'ssl.key.password': kafka_properties['ssl.key.password']
})

def apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type):
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
        logging.info(f"Applied ACL: {principal} {permission_type} {operation} on {restype}:{name} with pattern {resource_pattern_type} in namespace: {os.getenv('NAMESPACE')}")
    except Exception as e:
        logging.error(f"Failed to apply ACL: {e}")

def delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type):
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
        logging.info(f"Deleted ACL: {principal} {permission_type} {operation} on {restype}:{name} with pattern {resource_pattern_type} in namespace: {os.getenv('NAMESPACE')}")
    except Exception as e:
        logging.error(f"Failed to delete ACL: {e}")

def main():
    # Watch for changes to the KafkaACL CRD
    resource_version = ''
    while True:
        try:
            #stream = watch.Watch().stream(api.list_cluster_custom_object,
            stream = watch.Watch().stream(api.list_namespaced_custom_object,
                                          group="kafka.namespaced.com",
                                          version="v1alpha1",
                                          namespace= os.getenv('NAMESPACE'),
                                          #namespace="wowsome",
                                          plural="kafkaacls",
                                          resource_version=resource_version)

            for event in stream:
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
                    apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type)
                elif event_type == 'DELETED':
                    delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type)

        except Exception as e:
            logging.error(f"Error in main loop: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
