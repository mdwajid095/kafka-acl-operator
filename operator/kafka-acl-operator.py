import os
import time
import logging
from kubernetes import client, config, watch
from confluent_kafka.admin import AdminClient, AclBinding, AclBindingFilter, AclOperation, AclPermissionType, ResourceType, ResourcePatternType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load Kubernetes configuration
config.load_kube_config()

# Initialize Kubernetes API client
api = client.CustomObjectsApi()

# Kafka AdminClient configuration
kafka_admin_client = AdminClient({
    'bootstrap.servers': 'kafka.raittcs01.emp-dev.gcp.de.pri.o2.com:9092',
    'security.protocol': 'SSL',
    'ssl.ca.location': '/home/md_wajid_external_gcp_telefonica/tls-kafka-external/cacerts.pem',
    'ssl.certificate.location': '/home/md_wajid_external_gcp_telefonica/tls-kafka-external/fullchain.pem',
    'ssl.key.location': '/home/md_wajid_external_gcp_telefonica/tls-kafka-external/privkey.pem',
    'ssl.key.password': 'mystorepassword'  # Replace with your actual keystore password
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
        logging.info(f"Applied ACL: {principal} {permission_type} {operation} on {restype}:{name} with pattern {resource_pattern_type}")
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
        logging.info(f"Deleted ACL: {principal} {permission_type} {operation} on {restype}:{name} with pattern {resource_pattern_type}")
    except Exception as e:
        logging.error(f"Failed to delete ACL: {e}")

def main():
    # Watch for changes to the KafkaACL CRD
    resource_version = ''
    while True:
        try:
            stream = watch.Watch().stream(api.list_namespaced_custom_object,
                                          group="kafka.example.com",
                                          version="v1alpha1",
                                          namespace="confluent",
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
                resource_pattern_type = spec['patternType'] # Read pattern type

                if event_type == 'ADDED' or event_type == 'MODIFIED':
                    apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type)
                elif event_type == 'DELETED':
                    delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type)

        except Exception as e:
            logging.error(f"Error in main loop: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
