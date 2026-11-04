import os
import json
import joblib
import numpy as np
import logging
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from backend.models import SystemMetric, db

logger = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("ML_MODEL_PATH", "backend/ml/models/anomaly_detector.joblib")
SCALER_PATH = os.environ.get("ML_SCALER_PATH", "backend/ml/models/scaler.joblib")

CONTAMINATION = float(os.environ.get("ML_CONTAMINATION", "0.1"))
N_ESTIMATORS = int(os.environ.get("ML_N_ESTIMATORS", "100"))


class AnomalyDetector:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = ["cpu_percent", "memory_percent", "disk_percent", "process_count"]
        self._load_or_create_model()

    def _load_or_create_model(self):
        model_directory = os.path.dirname(MODEL_PATH)
        if model_directory:
            os.makedirs(model_directory, exist_ok=True)
        if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
                self.scaler = joblib.load(SCALER_PATH)
                self.is_trained = True
                print(f"Loaded existing model from {MODEL_PATH}")
            except Exception as e:
                print(f"Failed to load model: {e}, creating new model")
                self._create_new_model()
        else:
            self._create_new_model()

    def _create_new_model(self):
        self.model = IsolationForest(
            n_estimators=N_ESTIMATORS,
            contamination=CONTAMINATION,
            random_state=42,
            n_jobs=-1
        )
        self.is_trained = False

    def _extract_features(self, metric):
        return np.array([[
            metric.cpu_percent,
            metric.memory_percent,
            metric.disk_percent,
            metric.process_count
        ]])

    def _extract_features_from_dict(self, data):
        return np.array([[
            data.get("cpu_percent", 0),
            data.get("memory_percent", 0),
            data.get("disk_percent", 0),
            data.get("process_count", 0)
        ]])

    def train(self, device_id=None, hours=168):
        try:
            if self.is_trained:
                return True
            since = datetime.utcnow() - timedelta(hours=hours)
            query = SystemMetric.query.filter(SystemMetric.timestamp >= since)
            if device_id:
                from backend.models import Device
                device = Device.query.filter_by(device_id=device_id).first()
                if device:
                    query = query.filter_by(device_id=device.id)

            metrics = query.all()
            if len(metrics) < 50:
                logger.info("Insufficient data for training: %s samples (need at least 50)", len(metrics))
                return False

            X = np.array([[
                m.cpu_percent, m.memory_percent, m.disk_percent, m.process_count
            ] for m in metrics if all(
                np.isfinite(value) for value in (
                    m.cpu_percent, m.memory_percent, m.disk_percent, m.process_count
                )
            )])
            if len(X) < 50:
                logger.info("Insufficient valid data for training: %s samples (need at least 50)", len(X))
                return False

            X_scaled = self.scaler.fit_transform(X)
            self.model.fit(X_scaled)
            self.is_trained = True

            joblib.dump(self.model, MODEL_PATH)
            joblib.dump(self.scaler, SCALER_PATH)
            print(f"Model trained on {len(metrics)} samples and saved to {MODEL_PATH}")
            return True

        except Exception as e:
            print(f"Error training model: {e}")
            return False

    def predict(self, metric_data):
        if not self.is_trained:
            return {
                "anomaly_score": None,
                "is_anomaly": False,
                "label": "pending",
                "reason": "Model not trained yet - insufficient historical data",
                "recommendations": ["Collect more training data (minimum 50 samples)"]
            }

        try:
            X = self._extract_features_from_dict(metric_data)
            X_scaled = self.scaler.transform(X)

            anomaly_score = self.model.decision_function(X_scaled)[0]
            is_anomaly = self.model.predict(X_scaled)[0] == -1

            if is_anomaly:
                label = "critical" if anomaly_score < -0.5 else "warning"
            else:
                label = "normal"

            reason = self._generate_reason(metric_data, anomaly_score, is_anomaly)
            recommendations = self._generate_recommendations(metric_data, label)

            return {
                "anomaly_score": float(anomaly_score),
                "is_anomaly": bool(is_anomaly),
                "label": label,
                "reason": reason,
                "recommendations": recommendations
            }

        except Exception as e:
            print(f"Error predicting anomaly: {e}")
            return {
                "anomaly_score": None,
                "is_anomaly": False,
                "label": "pending",
                "reason": "ML prediction is temporarily unavailable",
                "recommendations": ["Continue collecting valid metric data"]
            }

    def _generate_reason(self, metric_data, anomaly_score, is_anomaly):
        if not is_anomaly:
            return "System metrics are within normal operating range"

        reasons = []
        cpu = metric_data.get("cpu_percent", 0)
        mem = metric_data.get("memory_percent", 0)
        disk = metric_data.get("disk_percent", 0)
        proc = metric_data.get("process_count", 0)

        if cpu > 80:
            reasons.append(f"High CPU utilization ({cpu:.1f}%)")
        if mem > 80:
            reasons.append(f"High memory utilization ({mem:.1f}%)")
        if disk > 85:
            reasons.append(f"High disk utilization ({disk:.1f}%)")
        if proc > 300:
            reasons.append(f"High process count ({proc})")

        if not reasons:
            reasons.append(f"Unusual system state detected (anomaly score: {anomaly_score:.3f})")

        return "; ".join(reasons)

    def _generate_recommendations(self, metric_data, label):
        recommendations = []
        cpu = metric_data.get("cpu_percent", 0)
        mem = metric_data.get("memory_percent", 0)
        disk = metric_data.get("disk_percent", 0)

        if label in ["warning", "critical"]:
            if cpu > 75:
                recommendations.append("Investigate high CPU processes and consider closing unnecessary applications")
            if mem > 75:
                recommendations.append("Check for memory leaks and close unused applications")
            if disk > 80:
                recommendations.append("Free up disk space by removing temporary files and unused programs")
            if label == "critical":
                recommendations.append("Immediate attention required - system may become unstable")
                recommendations.append("Consider restarting the system if performance is severely degraded")
        else:
            recommendations.append("System operating normally - continue monitoring")

        return recommendations

    def get_health_score(self, metric_data):
        prediction = self.predict(metric_data)
        if prediction["anomaly_score"] is None:
            return None
        anomaly_score = prediction["anomaly_score"]

        if prediction["label"] == "normal":
            score = max(0, min(100, 100 + anomaly_score * 50))
        elif prediction["label"] == "warning":
            score = max(0, min(70, 70 + anomaly_score * 30))
        else:
            score = max(0, min(40, 40 + anomaly_score * 20))

        return round(score, 1)


_detector_instance = None


def get_detector():
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AnomalyDetector()
    return _detector_instance


def analyze_metrics(metric_data):
    detector = get_detector()
    return detector.predict(metric_data)


def train_model(device_id=None):
    detector = get_detector()
    return detector.train(device_id)


def get_health_score(metric_data):
    detector = get_detector()
    return detector.get_health_score(metric_data)