import psutil
import platform
import socket
import time
import csv
import io
import shutil
import subprocess
from datetime import datetime


class MetricsCollector:
    def __init__(self):
        self._cpu_init = False

    def collect_system_info(self):
        gpu = self._collect_gpu()
        return {
            "hostname": socket.gethostname(),
            "os_info": f"{platform.system()} {platform.release()}",
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "total_memory": psutil.virtual_memory().total,
            "total_disk": psutil.disk_usage("/").total if platform.system() != "Windows" else psutil.disk_usage("C:\\").total,
            "boot_time": psutil.boot_time(),
            "gpu": gpu,
        }

    def _collect_gpu(self):
        unavailable = {
            "available": False,
            "name": None,
            "utilization_percent": None,
            "memory_percent": None,
            "memory_used": None,
            "memory_total": None,
            "temperature_c": None,
        }
        executable = shutil.which("nvidia-smi")
        if not executable:
            return unavailable
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            rows = list(csv.reader(io.StringIO(result.stdout), skipinitialspace=True))
            rows = [row for row in rows if len(row) == 5]
            if not rows:
                return unavailable

            def number(index):
                values = [float(row[index]) for row in rows if row[index].strip().lower() not in {"n/a", "[not supported]"}]
                return round(sum(values) / len(values), 2) if values else None

            memory_used = number(2)
            memory_total = number(3)
            return {
                "available": True,
                "name": ", ".join(row[0].strip() for row in rows),
                "utilization_percent": number(1),
                "memory_percent": round(memory_used / memory_total * 100, 2) if memory_used is not None and memory_total else None,
                "memory_used": memory_used,
                "memory_total": memory_total,
                "temperature_c": number(4),
            }
        except (OSError, subprocess.SubprocessError, ValueError):
            return unavailable

    def collect_metrics(self):
        if not self._cpu_init:
            psutil.cpu_percent(interval=0.1)
            self._cpu_init = True

        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
        uptime = time.time() - psutil.boot_time()

        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status", "username", "create_time", "exe", "cmdline"]):
            try:
                info = proc.info
                processes.append({
                    "pid": info["pid"],
                    "name": info["name"] or "Unknown",
                    "cpu_percent": info["cpu_percent"] or 0.0,
                    "memory_percent": info["memory_percent"] or 0.0,
                    "memory_used": info["memory_info"].rss if info["memory_info"] else 0,
                    "status": info["status"],
                    "username": info["username"],
                    "create_time": info["create_time"],
                    "exe": info["exe"],
                    "cmdline": " ".join(info["cmdline"]) if info["cmdline"] else None,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue

        metrics = {
            "cpu_percent": round(cpu_percent, 2),
            "memory_percent": round(memory.percent, 2),
            "memory_used": memory.used,
            "memory_total": memory.total,
            "disk_percent": round(disk.percent, 2),
            "disk_used": disk.used,
            "disk_total": disk.total,
            "process_count": len(processes),
            "uptime_seconds": int(uptime),
            "processes": processes,
            "timestamp": datetime.utcnow().isoformat()
        }
        metrics["gpu"] = self._collect_gpu()
        return metrics


def get_collector():
    return MetricsCollector()