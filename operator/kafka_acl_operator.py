#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import uuid
import random
import signal
import logging
import threading
import configparser
from dataclasses import dataclass
from typing import List, Optional, Iterable, Set, Tuple, Dict, Any
from collections import defaultdict
from time import monotonic

from kubernetes import client, config, watch
from kubernetes.client.exceptions import ApiException

from confluent_kafka.admin import (
    AdminClient,
    AclBinding,
    AclBindingFilter,
    AclOperation,
    AclPermissionType,
    ResourceType,
    ResourcePatternType,
)
from confluent_kafka import KafkaException

# ------------------------
# Logging
# ------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "JSON").upper()

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(record.created)),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge extra fields, when present
        for key in ("event", "principal", "restype", "cr_name", "event_type",
                    "count", "duration_ms", "error", "retry", "correlation_id",
                    "action", "audit"):
            if hasattr(record, key):
                base[key] = getattr(record, key)
        if record.exc_info:
            base["stack"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)

if LOG_FORMAT == "JSON":
    logging.basicConfig(level=LOG_LEVEL)
    for h in logging.getLogger().handlers:
        h.setFormatter(JSONFormatter())
else:
    logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

logger = logging.getLogger("acl-operator")

# ------------------------
# Configuration & Clients
# ------------------------
config_parser = configparser.ConfigParser()
adm_properties_path = os.getenv("ADM_PROPERTIES_PATH")
if not adm_properties_path or not os.path.exists(adm_properties_path):
    logger.critical("ADM_PROPERTIES_PATH env var missing or file not found", extra={"event": "startup"})
    raise SystemExit(2)
config_parser.read(adm_properties_path)
if "ACL_CONFIG" not in config_parser:
    logger.critical("ACL_CONFIG section missing in properties file", extra={"event": "startup"})
    raise SystemExit(2)

kafka_props = config_parser["ACL_CONFIG"]
required_props = [
    "bootstrap.servers",
]
missing = [k for k in required_props if not kafka_props.get(k)]
if missing:
    logger.critical("Missing required Kafka properties: %s", ",".join(missing), extra={"event": "startup"})
    raise SystemExit(2)

namespace = os.getenv("NAMESPACE", "confluent")
K8S_GROUP = os.getenv("K8S_GROUP", "emp.namespaced.com")
K8S_VERSION = os.getenv("K8S_VERSION", "v1alpha1")
K8S_PLURAL = os.getenv("K8S_PLURAL", "kafkaacls")
AUTHORITATIVE = os.getenv("AUTHORITATIVE", "true").strip().lower() == "true"
COLLAPSE_TO_ALL = os.getenv("COLLAPSE_TO_ALL", "true").strip().lower() == "true"
FULL_RECONCILE_INTERVAL_SECONDS = int(os.getenv("FULL_RECONCILE_INTERVAL_SECONDS", "0"))
WATCH_TIMEOUT_SECONDS = int(os.getenv("WATCH_TIMEOUT_SECONDS", "300"))
MAX_ACL_BATCH_SIZE = max(1, int(os.getenv("MAX_ACL_BATCH_SIZE", "100")))
MAX_RETRIES = max(0, int(os.getenv("MAX_RETRIES", "5")))
BACKOFF_BASE_SECONDS = float(os.getenv("BACKOFF_BASE_SECONDS", "0.5"))
BACKOFF_MAX_SECONDS = float(os.getenv("BACKOFF_MAX_SECONDS", "8"))
JITTER_SECONDS = float(os.getenv("JITTER_SECONDS", "0.2"))
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() == "true"

# Kubernetes config
try:
    config.load_incluster_config()
    logger.info("Loaded in-cluster Kubernetes configuration.", extra={"event": "startup"})
except config.config_exception.ConfigException:
    try:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig.", extra={"event": "startup"})
    except config.config_exception.ConfigException:
        logger.critical("Could not load Kubernetes configuration", extra={"event": "startup"})
        raise SystemExit(2)
api = client.CustomObjectsApi()

# Kafka Admin client
_kafka_admin_client = AdminClient({
    k: v for k, v in {
        "bootstrap.servers": kafka_props.get("bootstrap.servers"),
        "security.protocol": kafka_props.get("security.protocol"),
        "ssl.ca.location": kafka_props.get("ssl.ca.location"),
        "ssl.certificate.location": kafka_props.get("ssl.certificate.location"),
        "ssl.key.location": kafka_props.get("ssl.key.location"),
        "ssl.key.password": kafka_props.get("ssl.key.password"),
    }.items() if v
})

# ------------------------
# Operation mapping (meta roles -> concrete ops)
# ------------------------
OPERATION_MAPPING = {
    "CONSUMER": ["READ", "DESCRIBE", "DESCRIBE_CONFIGS"],
    "PRODUCER": ["WRITE", "DESCRIBE", "DESCRIBE_CONFIGS"],
    "PROSUMER": ["READ", "WRITE", "DESCRIBE", "DESCRIBE_CONFIGS"],
}

def coerce_list(x) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

def expand_operations(ops) -> List[str]:
    """Expand meta roles (e.g., PROSUMER) into concrete Kafka ACL operations."""
    expanded = set()
    for op in coerce_list(ops):
        key = str(op).upper()
        if key in OPERATION_MAPPING:
            expanded.update(OPERATION_MAPPING[key])
        else:
            expanded.add(key)
    return sorted(expanded)

# ------------------------
# Binding key / filters
# ------------------------
@dataclass(frozen=True)
class BindingKey:
    restype: ResourceType
    name: Optional[str]
    resource_pattern_type: ResourcePatternType
    principal: Optional[str]
    host: Optional[str]
    operation: AclOperation
    permission_type: AclPermissionType

def key_from_binding(b: AclBinding) -> BindingKey:
    return BindingKey(
        restype=b.restype,
        name=b.name,
        resource_pattern_type=b.resource_pattern_type,
        principal=b.principal,
        host=b.host,
        operation=b.operation,
        permission_type=b.permission_type,
    )

def exact_filter_from_key(k: BindingKey) -> AclBindingFilter:
    return AclBindingFilter(
        k.restype,
        k.name,
        k.resource_pattern_type,
        k.principal,
        k.host,
        k.operation,
        k.permission_type,
    )

# ------------------------
# Helpers: futures & batching
# ------------------------

def _iter_futures(res) -> Iterable:
    if res is None:
        return []
    if isinstance(res, dict):
        return res.values()
    if isinstance(res, (list, tuple, set)):
        return res
    if hasattr(res, "result"):
        return [res]
    raise TypeError(f"Unexpected AdminClient return type: {type(res)}")


def _batch(items: List[Any], n: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), n):
        yield items[i:i+n]

# ------------------------
# AdminClient call wrappers with retry/backoff & per-item logging
# ------------------------

def _sleep_backoff(attempt: int):
    backoff = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
    time.sleep(backoff + random.uniform(0, JITTER_SECONDS))


def _await_create_results(res, correlation_id: str, action: str):
    for fut in _iter_futures(res):
        try:
            fut.result()
        except Exception as e:
            logger.error(
                "Admin create ACL future failed",
                extra={"event": "admin_create_result", "error": str(e), "correlation_id": correlation_id, "action": action},
                exc_info=True,
            )
            raise


def _await_delete_results(res, correlation_id: str, action: str):
    for fut in _iter_futures(res):
        try:
            fut.result()
        except Exception as e:
            logger.error(
                "Admin delete ACL future failed",
                extra={"event": "admin_delete_result", "error": str(e), "correlation_id": correlation_id, "action": action},
                exc_info=True,
            )
            raise


def admin_create_acls(bindings: List[AclBinding], correlation_id: str, action: str):
    if DRY_RUN:
        logger.info(
            "[DRY-RUN] Would create %d ACL(s)", len(bindings),
            extra={"event": "create_acls", "count": len(bindings), "correlation_id": correlation_id, "action": action},
        )
        return
    attempt = 0
    while True:
        try:
            for chunk in _batch(bindings, MAX_ACL_BATCH_SIZE):
                res = _kafka_admin_client.create_acls(chunk)
                _await_create_results(res, correlation_id, action)
            return
        except KafkaException as ke:
            if attempt < MAX_RETRIES:
                attempt += 1
                logger.warning(
                    "create_acls retriable error; retrying",
                    extra={"event": "create_acls_retry", "retry": attempt, "error": str(ke), "correlation_id": correlation_id, "action": action},
                )
                _sleep_backoff(attempt)
                continue
            logger.error(
                "create_acls failed after retries",
                extra={"event": "create_acls_failed", "retry": attempt, "error": str(ke), "correlation_id": correlation_id, "action": action},
                exc_info=True,
            )
            raise
        except Exception as e:
            # Non-Kafka errors
            logger.error(
                "create_acls unexpected error",
                extra={"event": "create_acls_error", "error": str(e), "correlation_id": correlation_id, "action": action},
                exc_info=True,
            )
            raise


def admin_delete_acls(filters: List[AclBindingFilter], correlation_id: str, action: str):
    if DRY_RUN:
        logger.info(
            "[DRY-RUN] Would delete %d ACL(s)", len(filters),
            extra={"event": "delete_acls", "count": len(filters), "correlation_id": correlation_id, "action": action},
        )
        return
    attempt = 0
    while True:
        try:
            for chunk in _batch(filters, MAX_ACL_BATCH_SIZE):
                res = _kafka_admin_client.delete_acls(chunk)
                _await_delete_results(res, correlation_id, action)
            return
        except KafkaException as ke:
            if attempt < MAX_RETRIES:
                attempt += 1
                logger.warning(
                    "delete_acls retriable error; retrying",
                    extra={"event": "delete_acls_retry", "retry": attempt, "error": str(ke), "correlation_id": correlation_id, "action": action},
                )
                _sleep_backoff(attempt)
                continue
            logger.error(
                "delete_acls failed after retries",
                extra={"event": "delete_acls_failed", "retry": attempt, "error": str(ke), "correlation_id": correlation_id, "action": action},
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "delete_acls unexpected error",
                extra={"event": "delete_acls_error", "error": str(e), "correlation_id": correlation_id, "action": action},
                exc_info=True,
            )
            raise

# ------------------------
# Read current + build desired
# ------------------------

def fetch_current_acls(principal: str) -> List[AclBinding]:
    acl_filter = AclBindingFilter(
        ResourceType.ANY, None, ResourcePatternType.ANY,
        principal, None, AclOperation.ANY, AclPermissionType.ANY
    )
    future = _kafka_admin_client.describe_acls(acl_filter)
    return future.result()


def build_desired_for_principal(ns: str, principal: str) -> List[AclBinding]:
    desired: List[AclBinding] = []
    for item in list_all_crs(ns):
        spec = item.get("spec", {})
        if spec.get("principal") != principal:
            continue
        try:
            restype_enum = ResourceType[spec["resourceType"].upper()]
            permission_type_enum = AclPermissionType[spec["permissionType"].upper()]
            pattern_type_enum = ResourcePatternType[spec["patternType"].upper()]
            names = coerce_list(spec.get("resourceName", []))
            expanded_ops = expand_operations(spec.get("operation", []))
            host = (spec.get("host") or "*")
        except KeyError as e:
            logger.error(
                "Invalid CR spec (missing key)",
                extra={"event": "cr_parse_error", "error": str(e), "cr_name": item.get('metadata', {}).get('name')},
            )
            continue
        except Exception as e:
            logger.error(
                "Failed to parse CR spec",
                extra={"event": "cr_parse_error", "error": str(e), "cr_name": item.get('metadata', {}).get('name')},
                exc_info=True,
            )
            continue
        for n in names:
            for op in expanded_ops:
                try:
                    op_enum = AclOperation[op.upper()]
                except KeyError:
                    logger.error(
                        "Unknown operation in CR",
                        extra={"event": "cr_unknown_op", "cr_name": item.get('metadata', {}).get('name'), "error": op},
                    )
                    continue
                desired.append(
                    AclBinding(
                        restype_enum, n, pattern_type_enum,
                        principal, host, op_enum, permission_type_enum
                    )
                )
    return desired

# Collapse granular ops when ALL exists (same tuple)

def collapse_ops_when_all_present(bindings: List[AclBinding]) -> List[AclBinding]:
    groups = defaultdict(list)
    for b in bindings:
        base = (b.principal, b.restype, b.name, b.resource_pattern_type, b.host, b.permission_type)
        groups[base].append(b)
    result: List[AclBinding] = []
    for base, blist in groups.items():
        has_all = any(b.operation == AclOperation.ALL for b in blist)
        if has_all:
            result.extend([b for b in blist if b.operation == AclOperation.ALL])
        else:
            result.extend(blist)
    return result

# ------------------------
# Reconcile logic at (principal, resourceType)
# ------------------------

def reconcile_resource_type(ns: str, principal: str, restype: str):
    """Authoritatively reconcile ACLs for (principal, resourceType)."""
    corr = str(uuid.uuid4())
    t0 = monotonic()
    action = "reconcile_rtype"
    try:
        rt_enum = ResourceType[restype.upper()]
        # Build desired from CRs
        desired_all = build_desired_for_principal(ns, principal)
        desired_scoped = [b for b in desired_all if b.restype == rt_enum]
        if COLLAPSE_TO_ALL:
            desired_scoped = collapse_ops_when_all_present(desired_scoped)
        # Read current from cluster
        current_all = fetch_current_acls(principal)
        current_scoped = [b for b in current_all if b.restype == rt_enum]
        if COLLAPSE_TO_ALL:
            current_scoped = collapse_ops_when_all_present(current_scoped)
        current_map = {key_from_binding(b): b for b in current_scoped}
        desired_map = {key_from_binding(b): b for b in desired_scoped}
        to_create_keys = desired_map.keys() - current_map.keys()
        to_delete_keys = current_map.keys() - desired_map.keys()
        to_create = [desired_map[k] for k in to_create_keys]
        to_delete_filters = [exact_filter_from_key(k) for k in to_delete_keys]

        logger.info(
            "[RECONCILE:RTYPE] plan",
            extra={
                "event": "reconcile_plan", "principal": principal, "restype": restype,
                "count": {"create": len(to_create), "delete": len(to_delete_filters)},
                "correlation_id": corr, "action": action
            },
        )

        if to_create:
            admin_create_acls(to_create, corr, action)
        if AUTHORITATIVE and to_delete_filters:
            admin_delete_acls(to_delete_filters, corr, action)
        elif to_delete_filters:
            logger.info(
                "Non-authoritative mode: will not delete extras",
                extra={"event": "skip_delete", "principal": principal, "restype": restype, "count": len(to_delete_filters), "correlation_id": corr, "action": action},
            )
        dt = (monotonic() - t0) * 1000
        logger.info(
            "[RECONCILE:RTYPE] done",
            extra={"event": "reconcile_done", "principal": principal, "restype": restype, "duration_ms": int(dt), "correlation_id": corr, "action": action},
        )
    except Exception as e:
        dt = (monotonic() - t0) * 1000
        logger.error(
            "Error during resource-type reconcile",
            extra={"event": "reconcile_error", "principal": principal, "restype": restype, "duration_ms": int(dt), "error": str(e), "correlation_id": corr, "action": action},
            exc_info=True,
        )


def delete_all_for_resource_type(principal: str, restype: str):
    """Delete ALL ACLs for (principal, resourceType)."""
    corr = str(uuid.uuid4())
    action = "delete_rtype"
    try:
        rt_enum = ResourceType[restype.upper()]
        filt = AclBindingFilter(
            rt_enum,
            None,  # match all resource names
            ResourcePatternType.ANY,
            principal,
            None,  # match all hosts
            AclOperation.ANY,
            AclPermissionType.ANY,
        )
        logger.warning(
            "[DELETE:RTYPE] plan",
            extra={"event": "delete_plan", "principal": principal, "restype": restype, "correlation_id": corr, "action": action, "audit": True},
        )
        admin_delete_acls([filt], corr, action)
        logger.warning(
            "[DELETE:RTYPE] done",
            extra={"event": "delete_done", "principal": principal, "restype": restype, "correlation_id": corr, "action": action, "audit": True},
        )
    except Exception as e:
        logger.error(
            "Failed to delete all ACLs for (principal,restype)",
            extra={"event": "delete_error", "principal": principal, "restype": restype, "error": str(e), "correlation_id": corr, "action": action},
            exc_info=True,
        )

# ------------------------
# Kubernetes CR helpers (paging & listing)
# ------------------------

def list_all_crs(ns: str) -> List[dict]:
    """List all CRs with server-side paging (_continue)."""
    items: List[dict] = []
    _continue: Optional[str] = None
    while True:
        try:
            resp = api.list_namespaced_custom_object(
                group=K8S_GROUP,
                version=K8S_VERSION,
                namespace=ns,
                plural=K8S_PLURAL,
                limit=500,
                _continue=_continue,
            )
        except ApiException as ae:
            logger.error("CR list failed", extra={"event": "cr_list_error", "error": str(ae)})
            raise
        items.extend(resp.get("items", []))
        _continue = resp.get("metadata", {}).get("continue")
        if not _continue:
            break
    return items

# ------------------------
# Event processing (resource-type behavior)
# ------------------------

def process_event(event: dict, ns: str):
    obj = event.get("object", {})
    meta = obj.get("metadata", {})
    spec = obj.get("spec", {})
    etype = event.get("type")
    cr_name = meta.get("name")
    try:
        principal = spec["principal"]
        restype = spec["resourceType"]
    except KeyError as e:
        logger.error("KeyError in CR spec", extra={"event": "event_spec_error", "error": str(e), "cr_name": cr_name, "event_type": etype})
        return

    if etype in ("ADDED", "MODIFIED"):
        logger.info("CR %s received", etype, extra={"event": "event_received", "event_type": etype, "cr_name": cr_name, "principal": principal, "restype": restype})
        reconcile_resource_type(ns, principal, restype)
    elif etype == "DELETED":
        logger.info("CR DELETED received", extra={"event": "event_received", "event_type": etype, "cr_name": cr_name, "principal": principal, "restype": restype, "audit": True})
        delete_all_for_resource_type(principal, restype)
    else:
        logger.debug("Ignoring event type", extra={"event": "event_ignored", "event_type": etype, "cr_name": cr_name})

# ------------------------
# Watch & periodic reconcile
# ------------------------
_stop = threading.Event()

def watch_namespace():
    """Robust watch loop that handles 410 ResourceExpired and restarts the stream."""
    resource_version = ""
    while not _stop.is_set():
        try:
            # bootstrap list to get current resource_version if empty
            if not resource_version:
                resp = api.list_namespaced_custom_object(
                    group=K8S_GROUP,
                    version=K8S_VERSION,
                    namespace=namespace,
                    plural=K8S_PLURAL,
                    limit=1,
                )
                resource_version = resp.get("metadata", {}).get("resourceVersion", "")
            w = watch.Watch()
            stream = w.stream(
                api.list_namespaced_custom_object,
                group=K8S_GROUP,
                version=K8S_VERSION,
                namespace=namespace,
                plural=K8S_PLURAL,
                resource_version=resource_version,
                timeout_seconds=WATCH_TIMEOUT_SECONDS,
            )
            for event in stream:
                if _stop.is_set():
                    break
                obj = event.get("object", {})
                metadata = obj.get("metadata", {})
                rv = metadata.get("resourceVersion")
                if rv:
                    resource_version = rv
                process_event(event, namespace)
        except ApiException as ae:
            # 410 -> resourceVersion too old; reset and continue
            if ae.status == 410:
                logger.warning("Watch expired (410). Resetting resourceVersion and restarting.", extra={"event": "watch_reset"})
                resource_version = ""
                time.sleep(0.5)
                continue
            logger.error("API exception in watch loop", extra={"event": "watch_api_error", "error": str(ae)}, exc_info=True)
            time.sleep(1)
        except Exception as e:
            logger.error("Error in namespace watch loop", extra={"event": "watch_error", "error": str(e)}, exc_info=True)
            time.sleep(1)


def periodic_full_reconcile():
    if FULL_RECONCILE_INTERVAL_SECONDS <= 0:
        return
    logger.info(
        "Periodic reconcile enabled",
        extra={"event": "periodic_enabled", "count": FULL_RECONCILE_INTERVAL_SECONDS},
    )
    while not _stop.is_set():
        try:
            groups: Set[Tuple[str, str]] = set()
            for item in list_all_crs(namespace):
                spec = item.get("spec", {})
                principal = spec.get("principal")
                restype = spec.get("resourceType")
                if principal and restype:
                    groups.add((principal, restype))
            for (principal, restype) in groups:
                if _stop.is_set():
                    break
                reconcile_resource_type(namespace, principal, restype)
        except Exception as e:
            logger.error("Error during periodic reconcile", extra={"event": "periodic_error", "error": str(e)}, exc_info=True)
        # sleep in small chunks to observe stop sooner
        for _ in range(FULL_RECONCILE_INTERVAL_SECONDS):
            if _stop.is_set():
                break
            time.sleep(1)

# ------------------------
# Shutdown handling
# ------------------------

def handle_signal(signum, frame):
    logger.info("Signal received, shutting down...", extra={"event": "signal", "count": signum})
    _stop.set()


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    t_watch = threading.Thread(target=watch_namespace, name="watch", daemon=True)
    t_watch.start()

    t_periodic = None
    if FULL_RECONCILE_INTERVAL_SECONDS > 0:
        t_periodic = threading.Thread(target=periodic_full_reconcile, name="periodic", daemon=True)
        t_periodic.start()

    # keep main thread alive until stop
    try:
        while not _stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        _stop.set()

    t_watch.join(timeout=5)
    if t_periodic:
        t_periodic.join(timeout=5)

if __name__ == "__main__":
    main()
