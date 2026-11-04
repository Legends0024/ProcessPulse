import logging
import os
from datetime import datetime, timedelta
from flask import current_app
from backend.models import db, Device, SystemMetric, ProcessMetric, Alert, get_or_create_device
from sqlalchemy import func, desc

logger = logging.getLogger(__name__)


class MetricsService:
    @staticmethod
    def save_metrics(device_data, metrics_data):
        try:
            device = get_or_create_device(device_data)

            system_metric = SystemMetric(
                device_id=device.id,
                cpu_percent=metrics_data.get("cpu_percent", 0),
                memory_percent=metrics_data.get("memory_percent", 0),
                memory_used=metrics_data.get("memory_used", 0),
                memory_total=metrics_data.get("memory_total", 0),
                disk_percent=metrics_data.get("disk_percent", 0),
                disk_used=metrics_data.get("disk_used", 0),
                disk_total=metrics_data.get("disk_total", 0),
                process_count=metrics_data.get("process_count", 0),
                uptime_seconds=metrics_data.get("uptime_seconds", 0),
                gpu_available=bool(metrics_data.get("gpu", {}).get("available", False)),
                gpu_name=metrics_data.get("gpu", {}).get("name"),
                gpu_percent=metrics_data.get("gpu", {}).get("utilization_percent"),
                gpu_memory_percent=metrics_data.get("gpu", {}).get("memory_percent"),
                gpu_memory_used=metrics_data.get("gpu", {}).get("memory_used"),
                gpu_memory_total=metrics_data.get("gpu", {}).get("memory_total"),
                gpu_temperature=metrics_data.get("gpu", {}).get("temperature_c"),
            )
            db.session.add(system_metric)

            processes = metrics_data.get("processes", [])
            for proc in processes:
                process_metric = ProcessMetric(
                    device_id=device.id,
                    pid=proc.get("pid"),
                    name=proc.get("name", "Unknown"),
                    cpu_percent=proc.get("cpu_percent", 0),
                    memory_percent=proc.get("memory_percent", 0),
                    memory_used=proc.get("memory_used", 0),
                    status=proc.get("status"),
                    username=proc.get("username"),
                    create_time=datetime.fromtimestamp(proc["create_time"]) if proc.get("create_time") else None,
                    exe=proc.get("exe"),
                    cmdline=proc.get("cmdline"),
                )
                db.session.add(process_metric)

            db.session.commit()
            logger.info(f"Saved metrics for device {device.device_id}")
            return system_metric

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving metrics: {e}")
            raise

    @staticmethod
    def get_latest_metrics(device_id=None):
        query = SystemMetric.query
        if device_id:
            device = Device.query.filter_by(device_id=device_id).first()
            if not device:
                return None
            query = query.filter_by(device_id=device.id)
        return query.order_by(desc(SystemMetric.timestamp)).first()

    @staticmethod
    def get_metrics_history(device_id=None, hours=24, limit=1000):
        since = datetime.utcnow() - timedelta(hours=hours)
        query = SystemMetric.query.filter(SystemMetric.timestamp >= since)
        if device_id:
            device = Device.query.filter_by(device_id=device_id).first()
            if not device:
                return []
            query = query.filter_by(device_id=device.id)
        return query.order_by(SystemMetric.timestamp.asc()).limit(limit).all()

    @staticmethod
    def get_latest_processes(device_id=None, limit=100):
        query = ProcessMetric.query
        if device_id:
            device = Device.query.filter_by(device_id=device_id).first()
            if not device:
                return []
            query = query.filter_by(device_id=device.id)
        latest_time = query.with_entities(func.max(ProcessMetric.timestamp)).scalar()
        if not latest_time:
            return []
        return query.filter(ProcessMetric.timestamp == latest_time).order_by(
            desc(ProcessMetric.cpu_percent)
        ).limit(limit).all()

    @staticmethod
    def get_process_history(pid, device_id=None, hours=24, limit=500):
        since = datetime.utcnow() - timedelta(hours=hours)
        query = ProcessMetric.query.filter(
            ProcessMetric.pid == pid,
            ProcessMetric.timestamp >= since
        )
        if device_id:
            device = Device.query.filter_by(device_id=device_id).first()
            if device:
                query = query.filter_by(device_id=device.id)
        return query.order_by(ProcessMetric.timestamp.asc()).limit(limit).all()

    @staticmethod
    def analyze_resource_patterns(device_id=None, hours=24):
        metrics = MetricsService.get_metrics_history(device_id, hours, 1000)
        if len(metrics) < 2:
            return {
                "status": "insufficient_data",
                "sample_count": len(metrics),
                "message": "Collect at least 2 historical samples to analyze resource patterns.",
                "patterns": [],
                "top_processes": [],
                "recommendations": [],
            }

        first = metrics[0]
        latest = metrics[-1]
        elapsed_hours = max(
            (latest.timestamp - first.timestamp).total_seconds() / 3600,
            1 / 3600,
        )
        changes = {
            "cpu_percent": round(latest.cpu_percent - first.cpu_percent, 2),
            "memory_percent": round(latest.memory_percent - first.memory_percent, 2),
            "disk_percent": round(latest.disk_percent - first.disk_percent, 2),
        }
        patterns = []
        recommendations = []
        for field, label in (
            ("cpu_percent", "CPU"),
            ("memory_percent", "RAM"),
            ("disk_percent", "disk"),
        ):
            values = [getattr(metric, field) for metric in metrics]
            change = changes[field]
            rate = round(change / elapsed_hours, 2)
            maximum = max(values)
            if change >= 15 or rate >= 10:
                patterns.append({
                    "resource": field,
                    "label": label,
                    "start_percent": round(values[0], 2),
                    "current_percent": round(values[-1], 2),
                    "change_percent": change,
                    "rate_percent_per_hour": rate,
                    "peak_percent": round(maximum, 2),
                    "severity": "warning" if change < 30 else "critical",
                    "message": f"{label} usage increased {change:.1f} percentage points.",
                })
                if field == "memory_percent":
                    recommendations.append(
                        "Investigate the top memory-consuming processes for a possible memory leak."
                    )
                elif field == "cpu_percent":
                    recommendations.append(
                        "Review sustained CPU consumers and check whether a workload is stuck."
                    )
                else:
                    recommendations.append(
                        "Review disk growth and consider cleanup or retention adjustments."
                    )

        process_device_id = device_id
        top_processes = MetricsService.get_latest_processes(process_device_id, 10)
        top_processes.sort(key=lambda process: process.memory_percent or 0, reverse=True)
        top_processes = [
            {
                "pid": process.pid,
                "name": process.name,
                "memory_percent": process.memory_percent,
                "memory_used": process.memory_used,
                "cpu_percent": process.cpu_percent,
            }
            for process in top_processes[:5]
        ]
        if patterns and not recommendations:
            recommendations.append("Continue monitoring the increasing resource trend.")

        return {
            "status": "analyzed",
            "sample_count": len(metrics),
            "period_hours": hours,
            "changes": changes,
            "patterns": patterns,
            "top_processes": top_processes,
            "recommendations": list(dict.fromkeys(recommendations)),
        }


class AlertService:
    @staticmethod
    def create_alert(device_id, alert_type, severity, title, message, metric_value=None, threshold_value=None):
        alert = Alert(
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            metric_value=metric_value,
            threshold_value=threshold_value,
        )
        db.session.add(alert)
        db.session.commit()
        return alert

    @staticmethod
    def get_alerts(device_id=None, hours=24, limit=100, unacknowledged_only=False):
        since = datetime.utcnow() - timedelta(hours=hours)
        query = Alert.query.filter(Alert.timestamp >= since)
        if device_id:
            device = Device.query.filter_by(device_id=device_id).first()
            if not device:
                return []
            query = query.filter_by(device_id=device.id)
        if unacknowledged_only:
            query = query.filter_by(is_acknowledged=False)
        return query.order_by(desc(Alert.timestamp)).limit(limit).all()

    @staticmethod
    def acknowledge_alert(alert_id, acknowledged_by="user"):
        alert = db.session.get(Alert, alert_id)
        if alert:
            alert.is_acknowledged = True
            alert.acknowledged_at = datetime.utcnow()
            alert.acknowledged_by = acknowledged_by
            db.session.commit()
        return alert

    @staticmethod
    def check_thresholds(device_id, metrics):
        alerts = []
        cpu = metrics.get("cpu_percent", 0)
        mem = metrics.get("memory_percent", 0)
        disk = metrics.get("disk_percent", 0)

        if cpu >= 90:
            alerts.append(AlertService.create_alert(
                device_id, "high_cpu", "critical",
                "Critical CPU Usage", f"CPU usage is at {cpu:.1f}%",
                metric_value=cpu, threshold_value=90
            ))
        elif cpu >= 75:
            alerts.append(AlertService.create_alert(
                device_id, "high_cpu", "warning",
                "High CPU Usage", f"CPU usage is at {cpu:.1f}%",
                metric_value=cpu, threshold_value=75
            ))

        if mem >= 90:
            alerts.append(AlertService.create_alert(
                device_id, "high_memory", "critical",
                "Critical Memory Usage", f"Memory usage is at {mem:.1f}%",
                metric_value=mem, threshold_value=90
            ))
        elif mem >= 80:
            alerts.append(AlertService.create_alert(
                device_id, "high_memory", "warning",
                "High Memory Usage", f"Memory usage is at {mem:.1f}%",
                metric_value=mem, threshold_value=80
            ))

        if disk >= 95:
            alerts.append(AlertService.create_alert(
                device_id, "high_disk", "critical",
                "Critical Disk Usage", f"Disk usage is at {disk:.1f}%",
                metric_value=disk, threshold_value=95
            ))
        elif disk >= 85:
            alerts.append(AlertService.create_alert(
                device_id, "high_disk", "warning",
                "High Disk Usage", f"Disk usage is at {disk:.1f}%",
                metric_value=disk, threshold_value=85
            ))

        return alerts


class DeviceService:
    @staticmethod
    def get_all_devices():
        return Device.query.filter_by(is_active=True).all()

    @staticmethod
    def get_device(device_id):
        return Device.query.filter_by(device_id=device_id).first()

    @staticmethod
    def update_device_last_seen(device_id):
        device = Device.query.filter_by(device_id=device_id).first()
        if device:
            device.last_seen = datetime.utcnow()
            db.session.commit()
        return device

    @staticmethod
    def deactivate_device(device_id):
        device = Device.query.filter_by(device_id=device_id).first()
        if device:
            device.is_active = False
            db.session.commit()
        return device


class DataRetentionService:
    @staticmethod
    def cleanup_old_data(retention_days=None):
        if retention_days is None:
            retention_days = current_app.config.get("DATA_RETENTION_DAYS", 30)
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        deleted_metrics = SystemMetric.query.filter(SystemMetric.timestamp < cutoff).delete()
        deleted_processes = ProcessMetric.query.filter(ProcessMetric.timestamp < cutoff).delete()
        deleted_alerts = Alert.query.filter(Alert.timestamp < cutoff).delete()

        db.session.commit()
        logger.info(f"Cleaned up old data: {deleted_metrics} metrics, {deleted_processes} processes, {deleted_alerts} alerts")
        return {
            "metrics": deleted_metrics,
            "processes": deleted_processes,
            "alerts": deleted_alerts
        }