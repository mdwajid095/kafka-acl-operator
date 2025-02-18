import os
import time
import logging
import threading
import configparser
from kubernetes import client, config, watch
from confluent_kafka.admin import AdminClient, AclBinding, AclBindingFilter, AclOperation, AclPermissionType, ResourceType, ResourcePatternType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
kafka_properties = config_parser['ACL_CONFIG']
namespace = os.getenv('NAMESPACE', "confluent")

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
        permission_type_enum = AclPermissionType[permission_type.upper()]
        pattern_type_enum = ResourcePatternType[resource_pattern_type.upper()]

        for op in operation:
            operation_enum = AclOperation[op.upper()]
            for n in name:
                acl_binding = AclBinding(
                    restype_enum,
                    n,
                    pattern_type_enum,
                    principal,
                    '*',
                    operation_enum,
                    permission_type_enum
                )
                kafka_admin_client.create_acls([acl_binding])
                logging.info(f"Applied ACLs: {principal} {permission_type} {op} on {restype}:{n} with pattern {resource_pattern_type} in {scope}")
    except Exception as e:
        logging.error(f"Failed to apply ACL: {e}")

def delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope):
    try:
        restype_enum = ResourceType[restype.upper()]
        permission_type_enum = AclPermissionType[permission_type.upper()]
        pattern_type_enum = ResourcePatternType[resource_pattern_type.upper()]

        for op in operation:
            operation_enum = AclOperation[op.upper()]
            for n in name:
                acl_binding_filter = AclBindingFilter(
                    restype_enum,
                    n,
                    pattern_type_enum,
                    principal,
                    '*',
                    operation_enum,
                    permission_type_enum
                )
                kafka_admin_client.delete_acls([acl_binding_filter])
                logging.warning(f"Deleted ACLs: {principal} {permission_type} {op} on {restype}:{n} with pattern {resource_pattern_type} in {scope}")
    except Exception as e:
        logging.error(f"Failed to delete ACL: {e}")

def fetch_current_acls(principal):
    # Fetch current ACLs from Kafka cluster
    acl_filter = AclBindingFilter(
        restype=ResourceType.ANY,
        name=None,
        resource_pattern_type=ResourcePatternType.ANY,
        principal=principal,
        host="*",
        operation=AclOperation.ANY,
        permission_type=AclPermissionType.ANY
    )
    future = kafka_admin_client.describe_acls(acl_filter)
    acls = future.result()
    return acls

def fetch_desired_acls(operations):
    # Fetch desired ACLs from Kubernetes custom resources
    group = "emp.namespaced.com"
    version = "v1alpha1"
    plural = "kafkaacls"
    kafka_acls = api.list_namespaced_custom_object(group, version, namespace, plural)
    desired_acls = []
    for acl in kafka_acls.get('items', []):
        spec = acl['spec']
        principal = spec['principal']
        restype = spec['resourceType'].upper()
        name = spec['resourceName']
        resource_pattern_type = spec['patternType'].upper()
        operation = operations
        for resource_name in name:
            for op in operation:
                desired_acls.append(AclBinding(
                    restype=restype,
                    name=resource_name,
                    resource_pattern_type=resource_pattern_type,
                    principal=principal,
                    host="*",
                    operation=op,
                    permission_type=spec['permissionType']
                ))
    return desired_acls

def convert_acl_binding_to_filter(acl_binding):
    return AclBindingFilter(
        restype=acl_binding.restype,
        name=acl_binding.name,
        resource_pattern_type=acl_binding.resource_pattern_type,
        principal=acl_binding.principal,
        host=acl_binding.host,
        operation=acl_binding.operation,
        permission_type=acl_binding.permission_type
    )

def process_event(event, scope):
    event_type = event['type']
    kafka_acl = event['object']
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
    # meta operations
    operation_mapping = {
        'CONSUMER': ['READ', 'DESCRIBE', 'DESCRIBE_CONFIGS'],
        'PRODUCER': ['WRITE', 'DESCRIBE', 'DESCRIBE_CONFIGS'],
        'PROSUMER': ['READ', 'WRITE', 'DESCRIBE', 'DESCRIBE_CONFIGS']
    }
    meta_operations = set()
    for op in operation:
        if op in operation_mapping:
            meta_operations.update(operation_mapping[op])
        else:
            meta_operations.add(op)
    operation = list(meta_operations)

    if event_type == 'ADDED':
        apply_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)
    elif event_type == 'MODIFIED':
        # print(operation)
        try:
            current_acls = fetch_current_acls(principal)
            desired_acls = fetch_desired_acls(operation)

            acls_to_add = [acl for acl in desired_acls if acl not in current_acls]
            acls_to_delete = [acl for acl in current_acls if acl not in desired_acls]

            if acls_to_add:
                kafka_admin_client.create_acls(acls_to_add)
                logging.info(f"Applied ACLs: {acls_to_add}")
            if acls_to_delete:
                acl_binding_filters = [convert_acl_binding_to_filter(acl) for acl in acls_to_delete]
                kafka_admin_client.delete_acls(acl_binding_filters)
                logging.warning(f"Deleted ACLs: {acl_binding_filters}")
        except Exception as e:
            logging.error(f"Error during reconciliation: {e}")
    elif event_type == 'DELETED':
        delete_kafka_acl(principal, restype, name, operation, permission_type, resource_pattern_type, scope)

def watch_namespace():
    resource_version = ''
    while True:
        try:
            stream = watch.Watch().stream(api.list_namespaced_custom_object,
                                          group="emp.namespaced.com",
                                          version="v1alpha1",
                                          namespace=namespace,
                                          plural="kafkaacls",
                                          resource_version=resource_version)
            for event in stream:
                process_event(event, namespace)
        except Exception as e:
            logging.error(f"Error in namespace watch loop: {e}")
        time.sleep(1)

def main():
    # Create threads
    namespace_thread = threading.Thread(target=watch_namespace)
    # Start threads
    namespace_thread.start()
    # Wait for both threads to complete
    namespace_thread.join()

if __name__ == "__main__":
    main()
