from flask import Blueprint, jsonify, request, current_app
from backend.models import db, Device, SystemMetric, ProcessMetric, Alert, get_or_create_device
from backend.services import MetricsService, AlertService, DeviceService
from backend.ml import analyze_metrics, get_health_score, get_detector
from datetime import datetime, timedelta
import hashlib
import hmac
import secrets
from sqlalchemy import func, desc
import logging
import math
import psutil

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _hash_device_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _device_payload(device):
    payload = device.to_dict()
    timeout = current_app.config["HEARTBEAT_TIMEOUT_SECONDS"]
    age = (datetime.utcnow() - device.last_seen).total_seconds() if device.last_seen else None
    payload["is_online"] = bool(device.is_active and age is not None and age <= timeout)
    payload["status"] = "online" if payload["is_online"] else (
        "revoked" if not device.is_active else "offline"
    )
    payload["last_seen_age_seconds"] = round(age, 1) if age is not None else None
    return payload


def require_device_token(f):
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Device-Token")
        data = request.get_json(silent=True) or {}
        device_id = data.get("device", {}).get("device_id")
        device = Device.query.filter_by(device_id=device_id).first() if device_id else None
        if token and device and device.is_active and device.token_hash:
            if hmac.compare_digest(_hash_device_token(token), device.token_hash):
                return f(*args, **kwargs)
        if current_app.config.get("ALLOW_LEGACY_AGENT_TOKEN"):
            legacy = request.headers.get("X-Agent-Token") or request.args.get("token")
            configured = current_app.config.get("AGENT_TOKEN", "")
            if legacy and configured and hmac.compare_digest(legacy, configured):
                return f(*args, **kwargs)
        return jsonify({"error": "Invalid or missing device credential"}), 401
    decorated.__name__ = f.__name__
    return decorated


def require_agent_token(f):
    """Compatibility guard for local process-control requests."""
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Agent-Token")
        configured = current_app.config.get("AGENT_TOKEN", "")
        if not current_app.config.get("ALLOW_LEGACY_AGENT_TOKEN") or not token:
            return jsonify({"error": "Administrator authentication is required"}), 401
        if not configured or not hmac.compare_digest(token, configured):
            return jsonify({"error": "Invalid administrator credential"}), 401
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated


def require_admin_token(f):
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Admin-Token")
        configured = current_app.config.get("DEVICE_ADMIN_TOKEN", "")
        if not configured or not token or not hmac.compare_digest(token, configured):
            return jsonify({"error": "Invalid or missing administrator credential"}), 401
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated


@api_bp.route("/health", methods=["GET"])
def health_check():
    latest = MetricsService.get_latest_metrics()
    device = db.session.get(Device, latest.device_id) if latest else None
    age_seconds = None
    if latest and latest.timestamp:
        age_seconds = max(0, (datetime.utcnow() - latest.timestamp).total_seconds())
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "backend_url": request.host_url.rstrip("/"),
        "device": _device_payload(device) if device else None,
        "last_metric_at": latest.timestamp.isoformat() if latest else None,
        "metric_age_seconds": age_seconds,
        "gpu": latest.to_dict().get("gpu") if latest else None,
    })


@api_bp.route("/devices/register", methods=["POST"])
def register_device():
    enrollment = request.headers.get("X-Registration-Token")
    configured = current_app.config.get("DEVICE_REGISTRATION_TOKEN", "")
    if not configured or not enrollment or not hmac.compare_digest(enrollment, configured):
        return jsonify({"error": "Invalid or missing registration credential"}), 401

    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()
    if not device_id or len(device_id) > 64:
        return jsonify({"error": "device_id is required and must be at most 64 characters"}), 400

    device = Device.query.filter_by(device_id=device_id).first()
    if device and device.is_active and device.token_hash:
        return jsonify({"error": "Device is already registered"}), 409

    token = secrets.token_urlsafe(32)
    if not device:
        device = Device(device_id=device_id, name=data.get("name") or device_id)
        db.session.add(device)
    for field in (
        "name", "hostname", "os_info", "os_version", "architecture",
        "processor", "total_memory", "total_disk"
    ):
        if data.get(field) is not None:
            setattr(device, field, data[field])
    device.token_hash = _hash_device_token(token)
    device.is_active = True
    device.last_seen = datetime.utcnow()
    db.session.commit()
    return jsonify({
        "status": "registered",
        "device_id": device_id,
        "device_token": token,
    }), 201


@api_bp.route("/devices/<device_id>/revoke", methods=["POST"])
@require_admin_token
def revoke_device(device_id):
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return jsonify({"error": "Device not found"}), 404
    device.is_active = False
    device.token_hash = None
    db.session.commit()
    return jsonify({"status": "revoked", "device_id": device_id})


@api_bp.route("/metrics", methods=["POST"])
@require_device_token
def receive_metrics():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        device_data = data.get("device", {})
        metrics_data = data.get("metrics", {})

        if not device_data.get("device_id"):
            return jsonify({"error": "device_id is required"}), 400

        required_metrics = ["cpu_percent", "memory_percent", "disk_percent", "process_count", "uptime_seconds"]
        for field in required_metrics:
            if field not in metrics_data:
                return jsonify({"error": f"Missing required metric: {field}"}), 400
            value = metrics_data[field]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                return jsonify({"error": f"Invalid metric: {field}"}), 400

        for field in ("cpu_percent", "memory_percent", "disk_percent"):
            if not 0 <= metrics_data[field] <= 100:
                return jsonify({"error": f"Metric out of range: {field}"}), 400
        if metrics_data["process_count"] < 0 or metrics_data["uptime_seconds"] < 0:
            return jsonify({"error": "process_count and uptime_seconds must be non-negative"}), 400
        gpu = metrics_data.get("gpu")
        if gpu is not None and not isinstance(gpu, dict):
            return jsonify({"error": "gpu must be an object when provided"}), 400

        system_metric = MetricsService.save_metrics(device_data, metrics_data)

        detector = get_detector()
        if not detector.is_trained:
            detector.train(device_id=device_data["device_id"])
        analysis = analyze_metrics(metrics_data)
        health_score = get_health_score(metrics_data)

        system_metric.anomaly_score = analysis.get("anomaly_score")
        system_metric.anomaly_label = analysis.get("label")
        system_metric.anomaly_reason = analysis.get("reason")
        db.session.commit()

        alerts = AlertService.check_thresholds(system_metric.device_id, metrics_data)
        if analysis.get("is_anomaly"):
            alerts.append(AlertService.create_alert(
                system_metric.device_id, "anomaly_detected", analysis.get("label"),
                f"Anomaly Detected: {analysis.get('label').title()}",
                analysis.get("reason"),
                metric_value=analysis.get("anomaly_score")
            ))

        DeviceService.update_device_last_seen(device_data["device_id"])

        return jsonify({
            "status": "success",
            "metric_id": system_metric.id,
            "analysis": analysis,
            "health_score": health_score,
            "alerts_created": len(alerts)
        }), 201

    except Exception as e:
        logger.error(f"Error receiving metrics: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/latest", methods=["GET"])
def get_latest():
    device_id = request.args.get("device_id")
    metric = MetricsService.get_latest_metrics(device_id)
    if not metric:
        return jsonify({"error": "No metrics found"}), 404

    device = db.session.get(Device, metric.device_id)
    processes = MetricsService.get_latest_processes(device_id, limit=50)

    metric_data = {
        "cpu_percent": metric.cpu_percent,
        "memory_percent": metric.memory_percent,
        "disk_percent": metric.disk_percent,
        "process_count": metric.process_count
    }
    analysis = {
        "anomaly_score": metric.anomaly_score,
        "is_anomaly": metric.anomaly_label in {"warning", "critical"},
        "label": metric.anomaly_label,
        "reason": metric.anomaly_reason,
        "recommendations": []
    }
    if not metric.anomaly_label or metric.anomaly_label == "pending":
        analysis = analyze_metrics(metric_data)

    return jsonify({
        "device": _device_payload(device) if device else None,
        "metric": metric.to_dict(),
        "processes": [p.to_dict() for p in processes],
        "analysis": analysis,
        "health_score": get_health_score(metric_data)
    })


@api_bp.route("/history", methods=["GET"])
def get_history():
    device_id = request.args.get("device_id")
    hours = int(request.args.get("hours", 24))
    limit = int(request.args.get("limit", 1000))

    metrics = MetricsService.get_metrics_history(device_id, hours, limit)

    return jsonify({
        "metrics": [m.to_dict() for m in metrics],
        "count": len(metrics),
        "hours": hours
    })


@api_bp.route("/patterns", methods=["GET"])
def get_resource_patterns():
    device_id = request.args.get("device_id")
    try:
        hours = max(1, min(int(request.args.get("hours", 24)), 168))
    except ValueError:
        return jsonify({"error": "hours must be an integer"}), 400
    return jsonify(MetricsService.analyze_resource_patterns(device_id, hours))


@api_bp.route("/processes", methods=["GET"])
def get_processes():
    device_id = request.args.get("device_id")
    limit = int(request.args.get("limit", 100))
    sort_by = request.args.get("sort", "cpu_percent")
    order = request.args.get("order", "desc")

    processes = MetricsService.get_latest_processes(device_id, limit=limit * 2)

    valid_sorts = ["pid", "name", "cpu_percent", "memory_percent", "memory_used", "status"]
    if sort_by in valid_sorts:
        reverse = order == "desc"
        processes.sort(key=lambda p: getattr(p, sort_by, 0) or 0, reverse=reverse)

    return jsonify({
        "processes": [p.to_dict() for p in processes[:limit]],
        "count": len(processes[:limit])
    })


@api_bp.route("/processes/<int:pid>/history", methods=["GET"])
def get_process_history(pid):
    device_id = request.args.get("device_id")
    hours = int(request.args.get("hours", 24))
    limit = int(request.args.get("limit", 500))

    history = MetricsService.get_process_history(pid, device_id, hours, limit)

    return jsonify({
        "pid": pid,
        "history": [h.to_dict() for h in history],
        "count": len(history)
    })


@api_bp.route("/alerts", methods=["GET"])
def get_alerts():
    device_id = request.args.get("device_id")
    hours = int(request.args.get("hours", 24))
    limit = int(request.args.get("limit", 100))
    unacknowledged = request.args.get("unacknowledged", "false").lower() == "true"

    alerts = AlertService.get_alerts(device_id, hours, limit, unacknowledged)

    return jsonify({
        "alerts": [a.to_dict() for a in alerts],
        "count": len(alerts)
    })


@api_bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def acknowledge_alert(alert_id):
    data = request.get_json() or {}
    acknowledged_by = data.get("acknowledged_by", "user")
    alert = AlertService.acknowledge_alert(alert_id, acknowledged_by)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    return jsonify({"status": "success", "alert": alert.to_dict()})


@api_bp.route("/processes/<int:pid>/terminate", methods=["POST"])
@require_admin_token
def terminate_process(pid):
    """Terminate a confirmed, non-critical process after revalidation."""
    try:
        if pid <= 4:
            return jsonify({"error": "System and reserved process IDs cannot be terminated"}), 403

        data = request.get_json(silent=True) or {}
        process_name = str(data.get("name", "")).strip().lower()
        critical_processes = current_app.config.get("CRITICAL_PROCESSES", set())
        if process_name in {name.lower() for name in critical_processes}:
            return jsonify({"error": "Termination of critical system processes is prohibited"}), 403

        try:
            process = psutil.Process(pid)
            current_name = (process.name() or "").strip().lower()
        except psutil.NoSuchProcess:
            return jsonify({"error": "Process no longer exists"}), 404
        except psutil.AccessDenied:
            return jsonify({"error": "Permission denied while inspecting process"}), 403

        if process_name and current_name != process_name:
            return jsonify({"error": "Process changed before termination; refresh the process list"}), 409
        if current_name in {name.lower() for name in critical_processes}:
            return jsonify({"error": "Termination of critical system processes is prohibited"}), 403

        process.terminate()
        try:
            process.wait(timeout=3)
        except psutil.TimeoutExpired:
            return jsonify({"error": "Process did not exit within the safety timeout"}), 504
        logger.info("Terminated PID %s (%s) after explicit confirmation", pid, current_name)

        return jsonify({
            "status": "terminated",
            "message": f"Process {current_name} (PID {pid}) was terminated.",
            "pid": pid
        }), 200
    except psutil.AccessDenied:
        return jsonify({"error": "Permission denied while terminating process"}), 403
    except Exception as e:
        logger.error(f"Error processing termination for PID {pid}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/system", methods=["GET"])
def get_system_info():
    device_id = request.args.get("device_id")
    device = DeviceService.get_device(device_id) if device_id else Device.query.filter_by(is_active=True).first()

    if not device:
        return jsonify({"error": "No active device found"}), 404

    latest_metric = MetricsService.get_latest_metrics(device.device_id)
    processes = MetricsService.get_latest_processes(device.device_id, limit=10)

    return jsonify({
        "device": device.to_dict(),
        "current_metric": latest_metric.to_dict() if latest_metric else None,
        "top_processes": [p.to_dict() for p in processes],
        "health_score": get_health_score(latest_metric.__dict__) if latest_metric else 0
    })


@api_bp.route("/devices", methods=["GET"])
def get_devices():
    devices = DeviceService.get_all_devices()
    return jsonify({
        "devices": [_device_payload(d) for d in devices],
        "count": len(devices)
    })


@api_bp.route("/devices/<device_id>", methods=["GET"])
def get_device(device_id):
    device = DeviceService.get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    return jsonify(_device_payload(device))


@api_bp.route("/stats", methods=["GET"])
def get_stats():
    device_id = request.args.get("device_id")
    hours = int(request.args.get("hours", 24))

    since = datetime.utcnow() - timedelta(hours=hours)
    query = SystemMetric.query.filter(SystemMetric.timestamp >= since)
    if device_id:
        device = Device.query.filter_by(device_id=device_id).first()
        if device:
            query = query.filter_by(device_id=device.id)

    metrics = query.all()
    if not metrics:
        return jsonify({"error": "No data available"}), 404

    cpu_values = [m.cpu_percent for m in metrics]
    mem_values = [m.memory_percent for m in metrics]
    disk_values = [m.disk_percent for m in metrics]

    return jsonify({
        "period_hours": hours,
        "sample_count": len(metrics),
        "cpu": {
            "avg": round(sum(cpu_values) / len(cpu_values), 2),
            "min": round(min(cpu_values), 2),
            "max": round(max(cpu_values), 2),
        },
        "memory": {
            "avg": round(sum(mem_values) / len(mem_values), 2),
            "min": round(min(mem_values), 2),
            "max": round(max(mem_values), 2),
        },
        "disk": {
            "avg": round(sum(disk_values) / len(disk_values), 2),
            "min": round(min(disk_values), 2),
            "max": round(max(disk_values), 2),
        }
    })