from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, func

db = SQLAlchemy()


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    hostname = db.Column(db.String(256))
    os_info = db.Column(db.String(512))
    os_version = db.Column(db.String(128))
    architecture = db.Column(db.String(64))
    processor = db.Column(db.String(256))
    total_memory = db.Column(db.BigInteger)
    total_disk = db.Column(db.BigInteger)
    token_hash = db.Column(db.String(128), unique=True)
    is_active = db.Column(db.Boolean, default=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    metrics = db.relationship("SystemMetric", backref="device", lazy="dynamic", cascade="all, delete-orphan")
    processes = db.relationship("ProcessMetric", backref="device", lazy="dynamic", cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="device", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "name": self.name,
            "hostname": self.hostname,
            "os_info": self.os_info,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "processor": self.processor,
            "total_memory": self.total_memory,
            "total_disk": self.total_disk,
            "is_active": self.is_active,
            "status": "active" if self.is_active else "revoked",
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Device {self.device_id}: {self.name}>"


class SystemMetric(db.Model):
    __tablename__ = "system_metrics"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    cpu_percent = db.Column(db.Float, nullable=False)
    memory_percent = db.Column(db.Float, nullable=False)
    memory_used = db.Column(db.BigInteger, nullable=False)
    memory_total = db.Column(db.BigInteger, nullable=False)
    disk_percent = db.Column(db.Float, nullable=False)
    disk_used = db.Column(db.BigInteger, nullable=False)
    disk_total = db.Column(db.BigInteger, nullable=False)
    process_count = db.Column(db.Integer, nullable=False)
    uptime_seconds = db.Column(db.BigInteger, nullable=False)
    gpu_available = db.Column(db.Boolean, nullable=False, default=False)
    gpu_name = db.Column(db.String(256))
    gpu_percent = db.Column(db.Float)
    gpu_memory_percent = db.Column(db.Float)
    gpu_memory_used = db.Column(db.Float)
    gpu_memory_total = db.Column(db.Float)
    gpu_temperature = db.Column(db.Float)

    anomaly_score = db.Column(db.Float)
    anomaly_label = db.Column(db.String(32))
    anomaly_reason = db.Column(db.Text)

    __table_args__ = (
        Index("ix_system_metrics_device_timestamp", "device_id", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used": self.memory_used,
            "memory_total": self.memory_total,
            "disk_percent": self.disk_percent,
            "disk_used": self.disk_used,
            "disk_total": self.disk_total,
            "process_count": self.process_count,
            "uptime_seconds": self.uptime_seconds,
            "gpu": {
                "available": self.gpu_available,
                "name": self.gpu_name,
                "utilization_percent": self.gpu_percent,
                "memory_percent": self.gpu_memory_percent,
                "memory_used": self.gpu_memory_used,
                "memory_total": self.gpu_memory_total,
                "temperature_c": self.gpu_temperature,
            },
            "anomaly_score": self.anomaly_score,
            "anomaly_label": self.anomaly_label,
            "anomaly_reason": self.anomaly_reason,
        }

    def __repr__(self):
        return f"<SystemMetric device={self.device_id} cpu={self.cpu_percent} mem={self.memory_percent}>"


class ProcessMetric(db.Model):
    __tablename__ = "process_metrics"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    pid = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(256), nullable=False)
    cpu_percent = db.Column(db.Float, nullable=False)
    memory_percent = db.Column(db.Float, nullable=False)
    memory_used = db.Column(db.BigInteger, nullable=False)
    status = db.Column(db.String(64))
    username = db.Column(db.String(128))
    create_time = db.Column(db.DateTime)
    exe = db.Column(db.String(512))
    cmdline = db.Column(db.Text)

    __table_args__ = (
        Index("ix_process_metrics_device_timestamp", "device_id", "timestamp"),
        Index("ix_process_metrics_pid_timestamp", "pid", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "pid": self.pid,
            "name": self.name,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used": self.memory_used,
            "status": self.status,
            "username": self.username,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "exe": self.exe,
            "cmdline": self.cmdline,
        }

    def __repr__(self):
        return f"<ProcessMetric pid={self.pid} name={self.name} cpu={self.cpu_percent}>"


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    alert_type = db.Column(db.String(64), nullable=False)
    severity = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    message = db.Column(db.Text, nullable=False)
    metric_value = db.Column(db.Float)
    threshold_value = db.Column(db.Float)
    is_acknowledged = db.Column(db.Boolean, default=False)
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.String(128))

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "metric_value": self.metric_value,
            "threshold_value": self.threshold_value,
            "is_acknowledged": self.is_acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
        }

    def __repr__(self):
        return f"<Alert {self.severity}: {self.title}>"


def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _add_gpu_columns_for_existing_databases()
        _add_device_auth_columns_for_existing_databases()


def _add_gpu_columns_for_existing_databases():
    columns = {
        "gpu_available": "BOOLEAN NOT NULL DEFAULT FALSE",
        "gpu_name": "VARCHAR(256)",
        "gpu_percent": "FLOAT",
        "gpu_memory_percent": "FLOAT",
        "gpu_memory_used": "FLOAT",
        "gpu_memory_total": "FLOAT",
        "gpu_temperature": "FLOAT",
    }
    inspector = db.inspect(db.engine)
    existing = {column["name"] for column in inspector.get_columns("system_metrics")}
    for name, definition in columns.items():
        if name not in existing:
            db.session.execute(db.text(f"ALTER TABLE system_metrics ADD COLUMN {name} {definition}"))
    db.session.commit()


def _add_device_auth_columns_for_existing_databases():
    inspector = db.inspect(db.engine)
    existing = {column["name"] for column in inspector.get_columns("devices")}
    if "token_hash" not in existing:
        db.session.execute(db.text(
            "ALTER TABLE devices ADD COLUMN token_hash VARCHAR(128)"
        ))
        db.session.commit()


def get_or_create_device(device_data):
    device = Device.query.filter_by(device_id=device_data.get("device_id")).first()
    if not device:
        device = Device(
            device_id=device_data.get("device_id"),
            name=device_data.get("name", "Unknown Device"),
            hostname=device_data.get("hostname"),
            os_info=device_data.get("os_info"),
            os_version=device_data.get("os_version"),
            architecture=device_data.get("architecture"),
            processor=device_data.get("processor"),
            total_memory=device_data.get("total_memory"),
            total_disk=device_data.get("total_disk"),
        )
        db.session.add(device)
        db.session.commit()
    else:
        device.hostname = device_data.get("hostname", device.hostname)
        device.os_info = device_data.get("os_info", device.os_info)
        device.os_version = device_data.get("os_version", device.os_version)
        device.architecture = device_data.get("architecture", device.architecture)
        device.processor = device_data.get("processor", device.processor)
        device.total_memory = device_data.get("total_memory", device.total_memory)
        device.total_disk = device_data.get("total_disk", device.total_disk)
        device.is_active = True
        device.last_seen = datetime.utcnow()
        db.session.commit()
    return device