import os
import sys
import time
import json
import logging
import signal
import socket
import requests
from datetime import datetime
from dotenv import load_dotenv

try:
    from .collector import get_collector
except ImportError:
    from collector import get_collector

load_dotenv()

API_ENDPOINT = os.environ.get("API_ENDPOINT", "http://localhost:5000")
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "dev-agent-token-change-in-production")
DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "")
REGISTRATION_TOKEN = os.environ.get(
    "DEVICE_REGISTRATION_TOKEN", "dev-registration-token-change-in-production"
)
AGENT_INTERVAL = int(os.environ.get("AGENT_INTERVAL", "5"))
DEVICE_ID = os.environ.get("DEVICE_ID") or f"device-{socket.gethostname()}"
DEVICE_NAME = os.environ.get("DEVICE_NAME") or socket.gethostname()
TOKEN_FILE = os.environ.get("DEVICE_TOKEN_FILE", ".processpulse-device-token")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", mode="a")
    ]
)
logger = logging.getLogger(__name__)

shutdown_flag = False


def load_device_token():
    if DEVICE_TOKEN:
        return DEVICE_TOKEN
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as token_file:
            return token_file.read().strip()
    except FileNotFoundError:
        return ""
    except OSError as error:
        logger.warning("Unable to read device credential file: %s", error)
        return ""


def save_device_token(token):
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(token)
    except OSError as error:
        logger.error("Unable to save device credential file: %s", error)


def register_device(collector, session):
    device_info = collector.collect_system_info()
    payload = {
        "device_id": DEVICE_ID,
        "name": DEVICE_NAME,
        **{key: value for key, value in device_info.items() if key != "gpu"}
    }
    response = session.post(
        f"{API_ENDPOINT.rstrip('/')}/api/devices/register",
        json=payload,
        headers={"X-Registration-Token": REGISTRATION_TOKEN},
        timeout=10,
    )
    if response.status_code != 201:
        logger.error("Device registration failed with status %s", response.status_code)
        return ""
    token = response.json().get("device_token", "")
    if token:
        save_device_token(token)
    return token


def signal_handler(signum, frame):
    global shutdown_flag
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_flag = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def send_metrics(collector, session):
    try:
        device_token = load_device_token()
        if not device_token:
            device_token = register_device(collector, session)
            if not device_token:
                return False
        device_info = collector.collect_system_info()
        metrics = collector.collect_metrics()

        payload = {
            "device": {
                "device_id": DEVICE_ID,
                "name": DEVICE_NAME,
                **device_info
            },
            "metrics": metrics
        }

        headers = {
            "Content-Type": "application/json",
            "X-Device-Token": device_token,
        }

        response = session.post(
            f"{API_ENDPOINT.rstrip('/')}/api/metrics",
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 201:
            data = response.json()
            logger.info(f"Metrics sent successfully - Health Score: {data.get('health_score', 'N/A')}, "
                       f"Status: {data.get('analysis', {}).get('label', 'unknown')}, "
                       f"Alerts: {data.get('alerts_created', 0)}")
            return True
        elif response.status_code == 401:
            logger.error("Authentication failed - device may be revoked or credential invalid")
            return False
        else:
            logger.warning(f"Server returned {response.status_code}: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        logger.warning("Connection failed - backend may be down")
        return False
    except requests.exceptions.Timeout:
        logger.warning("Request timed out")
        return False
    except Exception as e:
        logger.error(f"Error sending metrics: {e}")
        return False


def main():
    logger.info("=" * 60)
    logger.info("ProcessPulse Agent Starting")
    logger.info(f"Device ID: {DEVICE_ID}")
    logger.info(f"Device Name: {DEVICE_NAME}")
    logger.info(f"API Endpoint: {API_ENDPOINT}")
    logger.info(f"Collection Interval: {AGENT_INTERVAL}s")
    logger.info("=" * 60)

    collector = get_collector()
    session = requests.Session()
    session.headers.update({"User-Agent": "ProcessPulse-Agent/1.0"})

    consecutive_failures = 0
    max_failures = 10

    try:
        while not shutdown_flag:
            start_time = time.time()

            success = send_metrics(collector, session)

            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    logger.error(f"Too many consecutive failures ({consecutive_failures}), exiting")
                    break

            elapsed = time.time() - start_time
            backoff = min(AGENT_INTERVAL * (2 ** min(consecutive_failures, 5)), 60)
            sleep_time = max(0, (backoff if consecutive_failures else AGENT_INTERVAL) - elapsed)

            for _ in range(int(sleep_time * 10)):
                if shutdown_flag:
                    break
                time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        logger.info("ProcessPulse Agent Stopped")


if __name__ == "__main__":
    main()