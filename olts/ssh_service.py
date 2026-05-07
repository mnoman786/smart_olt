"""
OLT Telnet service — ZTE and Huawei vendor drivers.

All CLI interaction uses Telnet (port 23 by default).
Paramiko / Netmiko are no longer required.
"""
from __future__ import annotations

import re
import socket
import logging
import random
import threading
import time
from contextlib import contextmanager

from django.conf import settings

logger = logging.getLogger(__name__)

_sem = threading.Semaphore(getattr(settings, 'OLT_SSH_MAX_CONCURRENT', 50))

DEMO_MODE: bool = getattr(settings, 'OLT_DEMO_MODE', False)
TELNET_TIMEOUT: int = getattr(settings, 'OLT_SSH_TIMEOUT', 30)

# CLI prompt endings — most OLT vendors use # or >
_PROMPT_ENDS = (b'#', b'>')

# Telnet protocol constants
_IAC  = 0xFF   # Interpret As Command
_WILL = 0xFB
_WONT = 0xFC
_DO   = 0xFD
_DONT = 0xFE
_SB   = 0xFA   # subnegotiation begin
_SE   = 0xF0   # subnegotiation end


# ── Raw-socket Telnet session ─────────────────────────────────────────────────

class TelnetSession:
    """
    Raw-socket Telnet client with proper IAC option negotiation.

    When the OLT sends DO/WILL option requests (terminal type, echo, window
    size …) we reply immediately with WONT/DONT so the device moves on to
    the login prompt without waiting.  This removes the long hang caused by
    unanswered negotiation frames.
    """

    def __init__(self, host: str, port: int, username: str, password: str,
                 timeout: int = 30):
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self._login(username, password)

    # ── IAC negotiation ───────────────────────────────────────────────────────

    def _process_iac(self, data: bytes) -> bytes:
        """
        Walk through raw bytes, reply to every IAC DO/WILL with WONT/DONT,
        skip subnegotiation blocks, and return the clean text portion.
        """
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b != _IAC:
                out.append(b)
                i += 1
                continue

            if i + 1 >= len(data):
                break

            cmd = data[i + 1]

            if cmd == _SB:
                # Skip everything until IAC SE
                end = data.find(bytes([_IAC, _SE]), i + 2)
                i = end + 2 if end != -1 else len(data)

            elif cmd in (_WILL, _DO, _WONT, _DONT) and i + 2 < len(data):
                opt = data[i + 2]
                # Reply: to DO → WONT,  to WILL → DONT
                if cmd == _DO:
                    self.sock.sendall(bytes([_IAC, _WONT, opt]))
                elif cmd == _WILL:
                    self.sock.sendall(bytes([_IAC, _DONT, opt]))
                # WONT / DONT need no reply
                i += 3

            else:
                # 2-byte command (e.g. IAC NOP)
                i += 2

        return bytes(out)

    def _read_until(self, *patterns: bytes, timeout: float | None = None) -> bytes:
        """
        Read from socket, process IAC frames (replying inline), accumulate
        clean text, and return once any pattern is found or timeout expires.
        """
        clean_buf = b''
        raw_buf   = b''
        deadline  = time.monotonic() + (timeout or self.timeout)
        self.sock.settimeout(0.3)
        try:
            while time.monotonic() < deadline:
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        break
                    raw_buf   += chunk
                    clean_buf  = self._process_iac(raw_buf)
                    if any(p in clean_buf for p in patterns):
                        return clean_buf
                except socket.timeout:
                    continue
        finally:
            self.sock.settimeout(self.timeout)
        return clean_buf

    def _send(self, text: str):
        self.sock.sendall(text.encode('ascii', errors='replace') + b'\r\n')

    # ── login ─────────────────────────────────────────────────────────────────

    def _login(self, username: str, password: str):
        # Read whatever the device sends first (banner + login prompt)
        initial = self._read_until(b'sername:', b'ogin:', b'#', b'>', timeout=self.timeout)

        if b'sername:' in initial or b'ogin:' in initial:
            self._send(username)
            after_user = self._read_until(b'assword:', b'#', b'>', timeout=self.timeout)
            if b'assword:' in after_user:
                self._send(password)
                after_pass = self._read_until(b'#', b'>', timeout=self.timeout)
                if not any(p in after_pass for p in _PROMPT_ENDS):
                    raise ConnectionError(
                        f'Login failed — wrong credentials or unexpected response: '
                        f'{after_pass[-200:].decode("ascii", errors="ignore")}'
                    )
        elif any(p in initial for p in _PROMPT_ENDS):
            pass  # no login prompt — already at CLI
        else:
            raise ConnectionError(
                f'Login failed — device sent unexpected banner: '
                f'{initial[-200:].decode("ascii", errors="ignore")}'
            )

        # ── privilege escalation ──────────────────────────────────────────────
        # Many OLTs land at an unprivileged prompt (> or >>) after login.
        # Send 'enable' and respond to the password prompt so we reach '#'
        # where all show/display commands are available.
        self._send('enable')
        enable_resp = self._read_until(b'assword:', b'#', timeout=self.timeout)
        if b'assword:' in enable_resp:
            self._send(password)
            self._read_until(b'#', b'>', timeout=self.timeout)
        # If already at # (or enable not required), just continue.

    # ── public API ────────────────────────────────────────────────────────────

    def send_command(self, cmd: str, timeout: int = 30) -> str:
        self._send(cmd)
        raw = self._read_until(b'#', b'>', timeout=timeout)
        return raw.decode('ascii', errors='ignore')

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ── Connection context manager ────────────────────────────────────────────────

@contextmanager
def _telnet_connection(olt):
    """Acquire semaphore slot, open Telnet session, yield, close."""
    _sem.acquire()
    session = None
    try:
        session = TelnetSession(
            host=str(olt.ip_address),
            port=olt.telnet_port,
            username=olt.username,
            password=olt.password,
            timeout=TELNET_TIMEOUT,
        )
        yield session
    finally:
        if session:
            session.close()
        _sem.release()


def _fmt(cmd_template: str, **kwargs) -> str:
    return cmd_template.format(**kwargs)


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
        m = re.search(
            r'[Uu]ptime[:\s]+(?:(\d+)\s*[Dd]ay[s]?)?\s*(?:(\d+)\s*[Hh](?:our[s]?)?)?\s*'
            r'(?:(\d+)\s*[Mm](?:in[a-z]*)?)?\s*(?:(\d+)\s*[Ss])',
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
        onts = []
        for line in output.splitlines():
            m = re.match(r'\s*gpon-onu_(\d+/\d+/\d+):(\d+)\s+(\S+)\s+(\S+)', line)
            if not m:
                continue
            port_str, ont_id, admin, phase = m.groups()
            status = 'online' if phase.lower() == 'working' else 'offline'
            onts.append({'port': port_str, 'ont_id': int(ont_id), 'status': status})
        return onts

    @staticmethod
    def parse_optical_info(output: str) -> dict:
        def _f(pattern: str) -> float:
            m = re.search(pattern, output, re.I)
            return float(m.group(1)) if m else 0.0

        return {
            'rx_power': _f(r'Rx optical power\(dBm\)[:\s]+([-\d.]+)'),
            'tx_power': _f(r'Tx optical power\(dBm\)[:\s]+([-\d.]+)'),
            'olt_rx_power': _f(r'OLT Rx optical power\(dBm\)[:\s]+([-\d.]+)'),
            'distance_m': int(_f(r'Distance\(m\)[:\s]+(\d+)')),
        }

    @staticmethod
    def parse_uncfg_list(output: str) -> list[dict]:
        results = []
        for line in output.splitlines():
            m = re.match(r'\s*-\s+([A-F0-9a-z]{12,16})\s+(\S+)\s+(\S+)', line)
            if m:
                serial, vendor_id, onu_type = m.groups()
                results.append({
                    'serial_number': serial.upper(),
                    'vendor_info': f'{vendor_id} {onu_type}'.strip(),
                })
        return results

    @staticmethod
    def parse_uncfg_all(output: str) -> list[dict]:
        results = []
        current_board, current_port = 1, 1
        for line in output.splitlines():
            m_port = re.search(r'gpon-olt_(\d+)/\d+/(\d+)', line)
            if m_port:
                current_board, current_port = int(m_port.group(1)), int(m_port.group(2))
                continue
            m = re.match(r'\s*-\s+([A-F0-9a-z]{12,16})\s+(\S+)\s+(\S+)', line)
            if m:
                serial, vendor_id, onu_type = m.groups()
                results.append({
                    'serial_number': serial.upper(),
                    'vendor_info': f'{vendor_id} {onu_type}'.strip(),
                    'board': current_board,
                    'port': current_port,
                })
        return results

    @staticmethod
    def parse_port_list(output: str) -> list[tuple]:
        ports = []
        for m in re.finditer(r'gpon-olt_(\d+)/\d+/(\d+)', output):
            board, port = int(m.group(1)), int(m.group(2))
            if (board, port) not in ports:
                ports.append((board, port))
        return ports

    @staticmethod
    def parse_ont_detail(output: str) -> list[dict]:
        results = []
        current: dict = {}
        for line in output.splitlines():
            m_idx = re.search(r'gpon-onu_\d+/\d+/\d+:(\d+)', line)
            if m_idx:
                if current:
                    results.append(current)
                current = {'ont_id': int(m_idx.group(1)), 'serial_number': '', 'status': 'offline', 'name': ''}
            m_sn = re.match(r'\s*SN\s*:\s*(\S+)', line)
            if m_sn and current:
                current['serial_number'] = m_sn.group(1).upper()
            m_name = re.match(r'\s*[Nn]ame\s*:\s*(.+)', line)
            if m_name and current:
                current['name'] = m_name.group(1).strip()
            m_state = re.match(r'\s*[Rr]un\s+[Ss]tate\s*:\s*(\S+)', line)
            if m_state and current:
                current['status'] = 'online' if m_state.group(1).lower() == 'working' else 'offline'
        if current:
            results.append(current)
        return results


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
            r'(?:(\d+)\s*day[s]?)?\s*(?:(\d+)\s*hour[s]?)?\s*'
            r'(?:(\d+)\s*minute[s]?)?\s*(?:(\d+)\s*second[s]?)?',
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
        onts = []
        for line in output.splitlines():
            m = re.match(
                r'\s*(\d+/\d+/\d+)\s+(\d+)\s+\S+\s+(\S+)\s+(online|offline)',
                line, re.I,
            )
            if not m:
                continue
            port_str, ont_id, _, run_state = m.groups()
            onts.append({'port': port_str, 'ont_id': int(ont_id), 'status': run_state.lower()})
        return onts

    @staticmethod
    def parse_optical_info(output: str) -> dict:
        def _f(pattern: str) -> float:
            m = re.search(pattern, output, re.I)
            return float(m.group(1)) if m else 0.0

        return {
            'rx_power': _f(r'RX\s+power\(dBm\)\s+([-\d.]+)'),
            'tx_power': _f(r'TX\s+power\(dBm\)\s+([-\d.]+)'),
            'olt_rx_power': _f(r'OLT\s+RX\s+power\(dBm\)\s+([-\d.]+)'),
            'distance_m': 0,
        }

    @staticmethod
    def parse_uncfg_list(output: str) -> list[dict]:
        results = []
        for line in output.splitlines():
            m = re.match(r'\s*[\d/]+\s+-\s+([A-Fa-f0-9]{16})\s+', line)
            if m:
                results.append({'serial_number': m.group(1).upper(), 'vendor_info': 'Huawei Auto-Found'})
        return results

    @staticmethod
    def parse_port_list(output: str) -> list[tuple]:
        ports = []
        for line in output.splitlines():
            m = re.match(r'\s*(\d+)\s+\S+GPFD\S*\s+Normal', line, re.I)
            if m:
                board = int(m.group(1))
                for p in range(8):
                    ports.append((board, p))
        return ports

    @staticmethod
    def parse_ont_detail(output: str) -> list[dict]:
        results = []
        current: dict = {}
        for line in output.splitlines():
            m_id = re.match(r'\s*ONT-ID\s*:\s*(\d+)', line, re.I)
            if m_id:
                if current:
                    results.append(current)
                current = {'ont_id': int(m_id.group(1)), 'serial_number': '', 'status': 'offline', 'name': ''}
            m_sn = re.match(r'\s*SN\s*:\s*(\S+)', line, re.I)
            if m_sn and current:
                current['serial_number'] = m_sn.group(1).upper()
            m_name = re.match(r'\s*[Dd]escription\s*:\s*(.+)', line)
            if m_name and current:
                current['name'] = m_name.group(1).strip()
            m_state = re.match(r'\s*[Rr]un\s+[Ss]tate\s*:\s*(\S+)', line, re.I)
            if m_state and current:
                current['status'] = 'online' if 'online' in m_state.group(1).lower() else 'offline'
        if current:
            results.append(current)
        return results


# ── Vendor command maps ───────────────────────────────────────────────────────

_VENDOR_COMMANDS = {
    'ZTE': {
        'version':       'show version',
        'cpu':           'show cpu',
        'memory':        'show memory',
        'temperature':   'show temperature',
        'port_list':     'show interface gpon-olt',
        'ont_list':      'show gpon onu state gpon-olt_{board}/{port_b}/{port}',
        'ont_detail':    'show gpon onu detail-info gpon-olt_{board}/{port_b}/{port}',
        'optical':       'show gpon onu optical-info interface gpon-onu_{board}/{port_b}/{port}:{ont_id}',
        'reboot':        'interface gpon-onu_{board}/{port_b}/{port}:{ont_id}\nreboot\nexit',
        'factory_reset': 'interface gpon-onu_{board}/{port_b}/{port}:{ont_id}\nfactory-reset\nexit',
        'uncfg_list':    'show gpon onu uncfg gpon-olt_{board}/{port_b}/{port}',
        'uncfg_all':     'show gpon onu uncfg',
    },
    'HUAWEI': {
        'version':       'display version',
        'cpu':           'display cpu-usage',
        'memory':        'display memory-usage',
        'temperature':   'display temperature 0',
        'port_list':     'display board 0',
        'ont_list':      'display ont info {board} {port} all',
        'ont_detail':    'display ont info {board} {port} all',
        'optical':       'display ont optical-info {board} {port} {ont_id}',
        'reboot':        'interface gpon {board}/{port}\nont reset {ont_id}\nquit',
        'factory_reset': 'interface gpon {board}/{port}\nont factory-reset {ont_id}\nquit',
        'uncfg_list':    'display ont autofind {board} {port}',
    },
}

_PARSERS = {'ZTE': ZTEParser, 'HUAWEI': HuaweiParser}


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
        'message': f'[DEMO] {command.replace("_", " ").title()} command simulated.',
        'output': '',
    }


# ── Public API ────────────────────────────────────────────────────────────────

def _test_telnet_raw(host: str, port: int, username: str, password: str) -> dict:
    """
    Open a Telnet session, log in, then close.
    Returns {connected, latency_ms, error}.
    """
    t0 = time.monotonic()
    try:
        session = TelnetSession(host=host, port=port, username=username,
                                password=password, timeout=TELNET_TIMEOUT)
        latency_ms = int((time.monotonic() - t0) * 1000)
        session.close()
        return {'connected': True, 'latency_ms': latency_ms, 'error': ''}
    except ConnectionError as exc:
        return {'connected': False, 'latency_ms': 0, 'error': str(exc)}
    except OSError as exc:
        return {'connected': False, 'latency_ms': 0,
                'error': f'Cannot reach {host}:{port} — {exc}'}
    except Exception as exc:
        return {'connected': False, 'latency_ms': 0, 'error': str(exc)}


def test_connection(olt) -> dict:
    """Test Telnet connectivity to an OLT."""
    if DEMO_MODE:
        return {
            'connected': True,
            'vendor': olt.vendor,
            'firmware': 'V2.0.1P2 (demo)',
            'latency_ms': random.randint(8, 40),
            'error': '',
        }

    result = _test_telnet_raw(
        host=str(olt.ip_address),
        port=olt.telnet_port,
        username=olt.username,
        password=olt.password,
    )
    return {
        'connected': result['connected'],
        'vendor': olt.vendor,
        'firmware': '',
        'latency_ms': result['latency_ms'],
        'error': result['error'],
    }


def poll_olt_stats_sync(olt) -> dict:
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
        from django.utils import timezone as _tz
        OLTMetrics.objects.create(
            olt=olt,
            timestamp=_tz.now(),
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
        with _telnet_connection(olt) as conn:
            cmds = _VENDOR_COMMANDS[olt.vendor]
            parser = _PARSERS[olt.vendor]

            v_out = conn.send_command(cmds['version'], timeout=TELNET_TIMEOUT)
            c_out = conn.send_command(cmds['cpu'],     timeout=TELNET_TIMEOUT)
            m_out = conn.send_command(cmds['memory'],  timeout=TELNET_TIMEOUT)
            t_out = conn.send_command(cmds['temperature'], timeout=TELNET_TIMEOUT)

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
        return {
            'connected': False, 'firmware': '', 'uptime_seconds': 0,
            'cpu_usage': 0.0, 'memory_usage': 0.0, 'temperature': 0.0,
            'error': str(exc),
        }


def poll_port_onts_sync(olt, board: int, port_b: int, port: int) -> list[dict]:
    if DEMO_MODE:
        return [
            {**_demo_optical(i), 'ont_id': i,
             'status': random.choice(['online', 'online', 'online', 'offline'])}
            for i in range(1, random.randint(4, 16))
        ]

    try:
        with _telnet_connection(olt) as conn:
            cmds = _VENDOR_COMMANDS[olt.vendor]
            parser = _PARSERS[olt.vendor]

            list_cmd = _fmt(cmds['ont_list'], board=board, port_b=port_b, port=port)
            list_out = conn.send_command(list_cmd, timeout=TELNET_TIMEOUT)
            onts = parser.parse_ont_list(list_out)

            results = []
            for ont in onts:
                optical_cmd = _fmt(
                    cmds['optical'],
                    board=board, port_b=port_b, port=port, ont_id=ont['ont_id'],
                )
                optical_out = conn.send_command(optical_cmd, timeout=TELNET_TIMEOUT)
                optical = parser.parse_optical_info(optical_out)
                results.append({**ont, **optical})
            return results
    except Exception as exc:
        logger.error('poll_port_onts OLT %s port %s/%s/%s: %s',
                     olt.ip_address, board, port_b, port, exc)
        return []


def send_ont_command_sync(ont, command: str) -> dict:
    if DEMO_MODE:
        return _demo_ont_command(command)

    olt = ont.olt
    if not ont.pon_port:
        return {'success': False, 'message': 'ONT has no PON port assigned.', 'output': ''}

    board  = ont.pon_port.board
    port_b = 1
    port   = ont.pon_port.port
    ont_id = ont.ont_id

    try:
        with _telnet_connection(olt) as conn:
            cmds = _VENDOR_COMMANDS[olt.vendor]
            cmd = _fmt(cmds[command], board=board, port_b=port_b, port=port, ont_id=ont_id)
            output = ''
            for line in cmd.splitlines():
                output += conn.send_command(line, timeout=TELNET_TIMEOUT)
            return {
                'success': True,
                'message': f'{command.replace("_", " ").title()} sent to ONT {ont.name}.',
                'output': output,
            }
    except Exception as exc:
        logger.error('send_ont_command ONT %s cmd=%s: %s', ont.serial_number, command, exc)
        return {'success': False, 'message': str(exc), 'output': ''}


def discover_unregistered_onts_sync(olt, pon_port) -> list[dict]:
    from onts.models import ONT
    from .models import DiscoveredONT

    if DEMO_MODE:
        rng = random.Random(pon_port.pk * 31337)
        fake_prefix  = 'ZTEG' if olt.vendor == 'ZTE' else '48575443'
        device_model = 'ZTE-F660' if olt.vendor == 'ZTE' else 'Huawei EG8145V5'
        stable_serials = [
            f'{fake_prefix}{rng.randint(10000000, 99999999):08d}' for _ in range(3)
        ]
        registered = set(ONT.objects.filter(pon_port=pon_port).values_list('serial_number', flat=True))
        found = [
            {'serial_number': s, 'vendor_info': f'{device_model} (demo)'}
            for s in stable_serials if s not in registered
        ]
    else:
        board  = pon_port.board
        port_b = 1
        port   = pon_port.port
        cmds   = _VENDOR_COMMANDS[olt.vendor]
        parser = _PARSERS[olt.vendor]

        try:
            with _telnet_connection(olt) as conn:
                cmd    = _fmt(cmds['uncfg_list'], board=board, port_b=port_b, port=port)
                output = conn.send_command(cmd, timeout=TELNET_TIMEOUT)
                found  = parser.parse_uncfg_list(output)
        except Exception as exc:
            logger.error('discover_unregistered_onts OLT %s port %s/%s: %s',
                         olt.ip_address, board, port, exc)
            return []

    registered   = set(ONT.objects.filter(pon_port=pon_port).values_list('serial_number', flat=True))
    unregistered = [f for f in found if f['serial_number'] not in registered]

    DiscoveredONT.objects.filter(pon_port=pon_port).delete()
    for entry in unregistered:
        DiscoveredONT.objects.update_or_create(
            pon_port=pon_port,
            serial_number=entry['serial_number'],
            defaults={'olt': olt, 'vendor_info': entry.get('vendor_info', '')},
        )

    return unregistered


def poll_all_ont_signals_sync(olt) -> int:
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

            db_ont.rx_power     = entry['rx_power']
            db_ont.tx_power     = entry['tx_power']
            db_ont.olt_rx_power = entry['olt_rx_power']
            db_ont.distance     = round(entry['distance_m'] / 1000, 2)
            db_ont.status       = entry['status']
            if entry['status'] == 'online':
                db_ont.last_online = timezone.now()
            db_ont.save(update_fields=['rx_power', 'tx_power', 'olt_rx_power',
                                       'distance', 'status', 'last_online'])

            SignalHistory.objects.create(
                ont=db_ont,
                timestamp=timezone.now(),
                rx_power=entry['rx_power'],
                tx_power=entry['tx_power'],
                olt_rx_power=entry['olt_rx_power'],
            )
            updated += 1

    return updated


def sync_olt_from_device_sync(olt) -> dict:
    from .models import PONPort
    from onts.models import ONT

    if DEMO_MODE:
        return {'ports_found': 0, 'onts_found': 0, 'error': 'demo mode — no real device'}

    cmds   = _VENDOR_COMMANDS.get(olt.vendor, {})
    parser = _PARSERS.get(olt.vendor)
    if not parser or not cmds:
        return {'ports_found': 0, 'onts_found': 0, 'error': f'Unsupported vendor: {olt.vendor}'}

    ports_found = 0
    onts_found  = 0
    error       = ''

    try:
        with _telnet_connection(olt) as conn:
            port_tuples: list[tuple] = []
            port_list_cmd = cmds.get('port_list', '')
            if port_list_cmd:
                try:
                    out = conn.send_command(port_list_cmd, timeout=TELNET_TIMEOUT)
                    port_tuples = parser.parse_port_list(out)
                except Exception:
                    pass

            if not port_tuples:
                port_tuples = [(1, p) for p in range(1, 17)]

            for board, port_num in port_tuples:
                ont_detail_cmd = _fmt(cmds.get('ont_detail', ''),
                                      board=board, port_b=1, port=port_num)
                try:
                    detail_out  = conn.send_command(ont_detail_cmd, timeout=TELNET_TIMEOUT)
                    ont_entries = parser.parse_ont_detail(detail_out)
                except Exception:
                    ont_entries = []

                if not ont_entries:
                    continue

                pon_port, created = PONPort.objects.get_or_create(
                    olt=olt, board=board, port=port_num,
                    defaults={'technology': 'GPON', 'max_onts': 128},
                )
                if created:
                    ports_found += 1

                for entry in ont_entries:
                    _, ont_created = ONT.objects.get_or_create(
                        olt=olt, pon_port=pon_port, ont_id=entry['ont_id'],
                        defaults={
                            'name': entry.get('name') or f"ONT-{entry['ont_id']}",
                            'serial_number': entry.get('serial_number', ''),
                            'status': entry.get('status', 'offline'),
                        },
                    )
                    if ont_created:
                        onts_found += 1

    except Exception as exc:
        logger.error('sync_olt_from_device OLT %s: %s', olt.ip_address, exc)
        error = str(exc)

    return {'ports_found': ports_found, 'onts_found': onts_found, 'error': error}


def scan_all_uncfg_sync(olt) -> list[dict]:
    if DEMO_MODE:
        rng    = random.Random(olt.pk * 99991)
        prefix = 'ZTEG' if olt.vendor == 'ZTE' else 'HWTC'
        return [
            {'serial_number': f'{prefix}{rng.randint(10000000,99999999):08d}',
             'vendor_info': f'{prefix} Demo-ONT',
             'board': 1, 'port': rng.randint(1, 8)}
            for _ in range(rng.randint(2, 8))
        ]

    cmds   = _VENDOR_COMMANDS.get(olt.vendor, {})
    parser = _PARSERS.get(olt.vendor)
    if not cmds or not parser:
        return []

    global_cmd = cmds.get('uncfg_all')
    if global_cmd and hasattr(parser, 'parse_uncfg_all'):
        try:
            with _telnet_connection(olt) as conn:
                out = conn.send_command(global_cmd, timeout=TELNET_TIMEOUT)
                return parser.parse_uncfg_all(out)
        except Exception as exc:
            logger.error('scan_all_uncfg OLT %s: %s', olt.ip_address, exc)
            return []

    results = []
    for pon_port in olt.pon_ports.all():
        found = discover_unregistered_onts_sync(olt, pon_port)
        for f in found:
            f['board'] = pon_port.board
            f['port']  = pon_port.port
            results.append(f)
    return results
