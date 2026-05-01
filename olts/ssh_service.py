"""
OLT SSH service — ZTE and Huawei vendor drivers.

Architecture for 1000+ OLTs:
  - Each Celery task calls connect() → do work → disconnect()
  - A Semaphore caps global concurrent SSH sessions (OLT_SSH_MAX_CONCURRENT)
  - Demo mode (OLT_DEMO_MODE=true) returns randomised but realistic data
    so the app works without real hardware
"""
from __future__ import annotations

import re
import logging
import random
import threading
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Global semaphore — shared across all threads / Celery workers on one machine.
# For multi-machine deployments use a Redis-backed distributed lock instead.
_sem = threading.Semaphore(getattr(settings, 'OLT_SSH_MAX_CONCURRENT', 50))

DEMO_MODE: bool = getattr(settings, 'OLT_DEMO_MODE', True)
SSH_TIMEOUT: int = getattr(settings, 'OLT_SSH_TIMEOUT', 30)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class OLTStats:
    connected: bool = False
    firmware: str = ''
    uptime_seconds: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    temperature: float = 0.0
    error: str = ''


@dataclass
class ONTOptical:
    ont_id: int = 0
    rx_power: float = 0.0
    tx_power: float = 0.0
    olt_rx_power: float = 0.0
    distance_m: int = 0
    status: str = 'unknown'


# ── Vendor parsers ────────────────────────────────────────────────────────────

class ZTEParser:
    """Parses CLI output from ZTE ZXAN OLTs (C300 / C320 / C600)."""

    @staticmethod
    def parse_cpu(output: str) -> float:
        m = re.search(r'CPU\s+\w+\s+usage[:\s]+(\d+(?:\.\d+)?)%', output, re.I)
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def parse_memory(output: str) -> float:
        m = re.search(r'[Mm]emory\s+usage[:\s]+(\d+(?:\.\d+)?)%', output, re.I)
        if m:
            return float(m.group(1))
        used = re.search(r'[Uu]sed\D+(\d+)[MmGg]', output)
        total = re.search(r'[Tt]otal\D+(\d+)[MmGg]', output)
        if used and total:
            return round(int(used.group(1)) / int(total.group(1)) * 100, 1)
        return 0.0

    @staticmethod
    def parse_temperature(output: str) -> float:
        m = re.search(r'[Tt]emperature[:\s]+(\d+(?:\.\d+)?)\s*[Cc°]', output)
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def parse_uptime(output: str) -> int:
        """Returns uptime in seconds."""
        m = re.search(
            r'[Uu]ptime[:\s]+(?:(\d+)\s*[Dd]ay[s]?)?\s*(?:(\d+)\s*[Hh](?:our[s]?)?)?\s*(?:(\d+)\s*[Mm](?:in[a-z]*)?)?\s*(?:(\d+)\s*[Ss])',
            output,
        )
        if not m:
            return 0
        d, h, mn, s = (int(x) if x else 0 for x in m.groups())
        return d * 86400 + h * 3600 + mn * 60 + s

    @staticmethod
    def parse_firmware(output: str) -> str:
        m = re.search(r'[Ss]oftware\s+[Vv]ersion[:\s]+(\S+)', output)
        return m.group(1) if m else ''

    @staticmethod
    def parse_ont_list(output: str) -> list[dict]:
        """Parse 'show gpon onu state gpon-olt_X/X/X' output."""
        onts = []
        for line in output.splitlines():
            m = re.match(
                r'\s*gpon-onu_(\d+/\d+/\d+):(\d+)\s+(\S+)\s+(\S+)',
                line,
            )
            if not m:
                continue
            port_str, ont_id, admin, phase = m.groups()
            status = 'online' if phase.lower() == 'working' else 'offline'
            onts.append({'port': port_str, 'ont_id': int(ont_id), 'status': status})
        return onts

    @staticmethod
    def parse_optical_info(output: str) -> dict:
        """Parse 'show gpon onu optical-info interface gpon-onu_X/X/X:Y'."""
        def _f(pattern: str) -> float:
            m = re.search(pattern, output, re.I)
            return float(m.group(1)) if m else 0.0

        return {
            'rx_power': _f(r'Rx optical power\(dBm\)[:\s]+([-\d.]+)'),
            'tx_power': _f(r'Tx optical power\(dBm\)[:\s]+([-\d.]+)'),
            'olt_rx_power': _f(r'OLT Rx optical power\(dBm\)[:\s]+([-\d.]+)'),
            'distance_m': int(_f(r'Distance\(m\)[:\s]+(\d+)')),
        }


class HuaweiParser:
    """Parses CLI output from Huawei MA56xx / MA58xx OLTs."""

    @staticmethod
    def parse_cpu(output: str) -> float:
        m = re.search(r'CPU\s+Usage\s*:\s*(\d+(?:\.\d+)?)%', output, re.I)
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def parse_memory(output: str) -> float:
        m = re.search(r'[Mm]emory\s+Using\s+Percentage\s+[Ii]s[:\s]+(\d+(?:\.\d+)?)%', output)
        if m:
            return float(m.group(1))
        m = re.search(r'(\d+(?:\.\d+)?)\s*%', output)
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def parse_temperature(output: str) -> float:
        m = re.search(r'\d+\s+\d+\s+(\d+(?:\.\d+)?)', output)
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def parse_uptime(output: str) -> int:
        m = re.search(
            r'(?:(\d+)\s*day[s]?)?\s*(?:(\d+)\s*hour[s]?)?\s*(?:(\d+)\s*minute[s]?)?\s*(?:(\d+)\s*second[s]?)?',
            output, re.I,
        )
        if not m or not any(m.groups()):
            return 0
        d, h, mn, s = (int(x) if x else 0 for x in m.groups())
        return d * 86400 + h * 3600 + mn * 60 + s

    @staticmethod
    def parse_firmware(output: str) -> str:
        m = re.search(r'[Vv]ersion\s+(\S+)', output)
        return m.group(1) if m else ''

    @staticmethod
    def parse_ont_list(output: str) -> list[dict]:
        """Parse 'display ont info' output."""
        onts = []
        for line in output.splitlines():
            m = re.match(
                r'\s*(\d+/\d+/\d+)\s+(\d+)\s+\S+\s+(\S+)\s+(online|offline)',
                line, re.I,
            )
            if not m:
                continue
            port_str, ont_id, _, run_state = m.groups()
            onts.append({
                'port': port_str,
                'ont_id': int(ont_id),
                'status': run_state.lower(),
            })
        return onts

    @staticmethod
    def parse_optical_info(output: str) -> dict:
        """Parse 'display ont optical-info' output."""
        def _f(pattern: str) -> float:
            m = re.search(pattern, output, re.I)
            return float(m.group(1)) if m else 0.0

        return {
            'rx_power': _f(r'RX\s+power\(dBm\)\s+([-\d.]+)'),
            'tx_power': _f(r'TX\s+power\(dBm\)\s+([-\d.]+)'),
            'olt_rx_power': _f(r'OLT\s+RX\s+power\(dBm\)\s+([-\d.]+)'),
            'distance_m': 0,
        }


# ── Vendor command maps ───────────────────────────────────────────────────────

_VENDOR_COMMANDS = {
    'ZTE': {
        'version':     'show version',
        'cpu':         'show cpu',
        'memory':      'show memory',
        'temperature': 'show temperature',
        'ont_list':    'show gpon onu state gpon-olt_{board}/{port_b}/{port}',
        'optical':     'show gpon onu optical-info interface gpon-onu_{board}/{port_b}/{port}:{ont_id}',
        'reboot':      'interface gpon-onu_{board}/{port_b}/{port}:{ont_id}\nreboot\nexit',
        'factory_reset': 'interface gpon-onu_{board}/{port_b}/{port}:{ont_id}\nfactory-reset\nexit',
    },
    'HUAWEI': {
        'version':     'display version',
        'cpu':         'display cpu-usage',
        'memory':      'display memory-usage',
        'temperature': 'display temperature 0',
        'ont_list':    'display ont info {board} {port} all',
        'optical':     'display ont optical-info {board} {port} {ont_id}',
        'reboot':      'interface gpon {board}/{port}\nont reset {ont_id}\nquit',
        'factory_reset': 'interface gpon {board}/{port}\nont factory-reset {ont_id}\nquit',
    },
}

_PARSERS = {'ZTE': ZTEParser, 'HUAWEI': HuaweiParser}

_DEVICE_TYPE = {
    'ZTE': 'generic_termserver',
    'HUAWEI': 'huawei_vrp',
}


# ── Connection context manager ────────────────────────────────────────────────

@contextmanager
def _ssh_connection(olt):
    """Acquire semaphore slot, open Netmiko connection, yield, close."""
    _sem.acquire()
    conn = None
    try:
        from netmiko import ConnectHandler
        conn = ConnectHandler(
            device_type=_DEVICE_TYPE.get(olt.vendor, 'generic_termserver'),
            host=str(olt.ip_address),
            port=olt.ssh_port,
            username=olt.username,
            password=olt.password,
            timeout=SSH_TIMEOUT,
            session_timeout=SSH_TIMEOUT + 30,
            fast_cli=False,
        )
        yield conn
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass
        _sem.release()


def _fmt(cmd_template: str, **kwargs) -> str:
    return cmd_template.format(**kwargs)


# ── Demo-mode helpers ─────────────────────────────────────────────────────────

def _demo_olt_stats(olt) -> dict:
    return {
        'connected': True,
        'firmware': 'V2.0.1P2 (demo)',
        'uptime_seconds': random.randint(86400, 86400 * 30),
        'cpu_usage': round(random.uniform(10, 65), 1),
        'memory_usage': round(random.uniform(30, 75), 1),
        'temperature': round(random.uniform(35, 52), 1),
        'error': '',
    }


def _demo_optical(ont_id: int) -> dict:
    rx = round(random.uniform(-30, -16), 2)
    return {
        'rx_power': rx,
        'tx_power': round(random.uniform(1.5, 4.0), 2),
        'olt_rx_power': round(rx - random.uniform(0.3, 1.5), 2),
        'distance_m': random.randint(500, 12000),
    }


def _demo_ont_command(command: str) -> dict:
    return {
        'success': True,
        'message': f'[DEMO] {command.replace("_", " ").title()} command simulated — no real OLT connected.',
        'output': '',
    }


# ── Public API ────────────────────────────────────────────────────────────────

def test_connection(olt) -> dict:
    """
    Test SSH connectivity to an OLT.
    Returns dict: {connected, vendor, firmware, latency_ms, error}
    """
    if DEMO_MODE:
        return {
            'connected': True,
            'vendor': olt.vendor,
            'firmware': 'V2.0.1P2 (demo)',
            'latency_ms': random.randint(8, 40),
            'error': '',
        }

    import time
    t0 = time.monotonic()
    try:
        with _ssh_connection(olt) as conn:
            cmds = _VENDOR_COMMANDS[olt.vendor]
            parser = _PARSERS[olt.vendor]
            output = conn.send_command(cmds['version'], read_timeout=SSH_TIMEOUT)
            latency_ms = int((time.monotonic() - t0) * 1000)
            return {
                'connected': True,
                'vendor': olt.vendor,
                'firmware': parser.parse_firmware(output),
                'latency_ms': latency_ms,
                'error': '',
            }
    except Exception as exc:
        logger.error('test_connection OLT %s: %s', olt.ip_address, exc)
        return {
            'connected': False,
            'vendor': olt.vendor,
            'firmware': '',
            'latency_ms': 0,
            'error': str(exc),
        }


def poll_olt_stats_sync(olt) -> dict:
    """
    Poll OLT for CPU / memory / temperature / uptime.
    Updates the OLT model in-place and returns the stats dict.
    Called synchronously when Celery is unavailable.
    """
    if DEMO_MODE:
        data = _demo_olt_stats(olt)
    else:
        data = _fetch_olt_stats(olt)

    if data['connected']:
        olt.cpu_usage = data['cpu_usage']
        olt.memory_usage = data['memory_usage']
        olt.temperature = data['temperature']
        if data.get('uptime_seconds'):
            olt.uptime = data['uptime_seconds']
        if data.get('firmware'):
            olt.firmware_version = data['firmware']
        olt.status = 'online'
        olt.save(update_fields=['cpu_usage', 'memory_usage', 'temperature',
                                'uptime', 'firmware_version', 'status'])

        from monitoring.models import OLTMetrics
        OLTMetrics.objects.create(
            olt=olt,
            cpu_usage=data['cpu_usage'],
            memory_usage=data['memory_usage'],
            temperature=data['temperature'],
        )
    else:
        olt.status = 'offline'
        olt.save(update_fields=['status'])

    return data


def _fetch_olt_stats(olt) -> dict:
    try:
        with _ssh_connection(olt) as conn:
            cmds = _VENDOR_COMMANDS[olt.vendor]
            parser = _PARSERS[olt.vendor]

            v_out = conn.send_command(cmds['version'], read_timeout=SSH_TIMEOUT)
            c_out = conn.send_command(cmds['cpu'], read_timeout=SSH_TIMEOUT)
            m_out = conn.send_command(cmds['memory'], read_timeout=SSH_TIMEOUT)
            t_out = conn.send_command(cmds['temperature'], read_timeout=SSH_TIMEOUT)

            return {
                'connected': True,
                'firmware': parser.parse_firmware(v_out),
                'uptime_seconds': parser.parse_uptime(v_out),
                'cpu_usage': parser.parse_cpu(c_out),
                'memory_usage': parser.parse_memory(m_out),
                'temperature': parser.parse_temperature(t_out),
                'error': '',
            }
    except Exception as exc:
        logger.error('poll_olt_stats OLT %s: %s', olt.ip_address, exc)
        return OLTStats(connected=False, error=str(exc)).__dict__


def poll_port_onts_sync(olt, board: int, port_b: int, port: int) -> list[dict]:
    """
    Fetch live ONT list + optical power for one PON port.
    Returns list of dicts: {ont_id, status, rx_power, tx_power, olt_rx_power, distance_m}
    """
    if DEMO_MODE:
        return [
            {**_demo_optical(i), 'ont_id': i,
             'status': random.choice(['online', 'online', 'online', 'offline'])}
            for i in range(1, random.randint(4, 16))
        ]

    try:
        with _ssh_connection(olt) as conn:
            cmds = _VENDOR_COMMANDS[olt.vendor]
            parser = _PARSERS[olt.vendor]

            list_cmd = _fmt(cmds['ont_list'], board=board, port_b=port_b, port=port)
            list_out = conn.send_command(list_cmd, read_timeout=SSH_TIMEOUT)
            onts = parser.parse_ont_list(list_out)

            results = []
            for ont in onts:
                optical_cmd = _fmt(
                    cmds['optical'],
                    board=board, port_b=port_b, port=port, ont_id=ont['ont_id'],
                )
                optical_out = conn.send_command(optical_cmd, read_timeout=SSH_TIMEOUT)
                optical = parser.parse_optical_info(optical_out)
                results.append({**ont, **optical})
            return results
    except Exception as exc:
        logger.error('poll_port_onts OLT %s port %s/%s/%s: %s',
                     olt.ip_address, board, port_b, port, exc)
        return []


def send_ont_command_sync(ont, command: str) -> dict:
    """
    Send a command ('reboot' or 'factory_reset') to a single ONT via SSH.
    `ont` is an ONT model instance with olt, pon_port FK populated.
    """
    if DEMO_MODE:
        return _demo_ont_command(command)

    olt = ont.olt
    if not ont.pon_port:
        return {'success': False, 'message': 'ONT has no PON port assigned.', 'output': ''}

    board = ont.pon_port.board
    port_b = 1   # ZTE uses board/slot/port — slot defaults to 1
    port = ont.pon_port.port
    ont_id = ont.ont_id

    try:
        with _ssh_connection(olt) as conn:
            cmds = _VENDOR_COMMANDS[olt.vendor]
            cmd = _fmt(cmds[command], board=board, port_b=port_b, port=port, ont_id=ont_id)
            output = ''
            for line in cmd.splitlines():
                output += conn.send_command_timing(line, read_timeout=SSH_TIMEOUT)
            return {
                'success': True,
                'message': f'{command.replace("_", " ").title()} sent to ONT {ont.name}.',
                'output': output,
            }
    except Exception as exc:
        logger.error('send_ont_command ONT %s cmd=%s: %s', ont.serial_number, command, exc)
        return {'success': False, 'message': str(exc), 'output': ''}


def poll_all_ont_signals_sync(olt) -> int:
    """
    Walk every PON port on the OLT, fetch optical data for all ONTs,
    and update the DB. Returns the number of ONTs updated.
    """
    from onts.models import ONT
    from monitoring.models import SignalHistory
    from django.utils import timezone

    updated = 0
    for port in olt.pon_ports.all():
        live = poll_port_onts_sync(olt, port.board, 1, port.port)
        for entry in live:
            try:
                db_ont = ONT.objects.get(olt=olt, pon_port=port, ont_id=entry['ont_id'])
            except ONT.DoesNotExist:
                continue

            db_ont.rx_power = entry['rx_power']
            db_ont.tx_power = entry['tx_power']
            db_ont.olt_rx_power = entry['olt_rx_power']
            db_ont.distance = round(entry['distance_m'] / 1000, 2)
            db_ont.status = entry['status']
            if entry['status'] == 'online':
                db_ont.last_online = timezone.now()
            db_ont.save(update_fields=['rx_power', 'tx_power', 'olt_rx_power',
                                       'distance', 'status', 'last_online'])

            SignalHistory.objects.create(
                ont=db_ont,
                rx_power=entry['rx_power'],
                tx_power=entry['tx_power'],
                olt_rx_power=entry['olt_rx_power'],
            )
            updated += 1

    return updated
