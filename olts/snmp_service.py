"""
SNMP service for OLT monitoring.

Uses puresnmp — a modern, pure-Python SNMP library with no legacy dependencies.
Install:  pip install puresnmp
"""
from __future__ import annotations
import asyncio
import logging
import sys

# ProactorEventLoop (Windows default) leaves UDP sockets dangling on close.
# SelectorEventLoop handles UDP cleanly and works fine for SNMP polling.
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)

# ── Standard MIB-II OIDs ─────────────────────────────────────────────────────
OID_SYS_DESCR  = '1.3.6.1.2.1.1.1.0'
OID_SYS_UPTIME = '1.3.6.1.2.1.1.3.0'

# ── ZTE ZXAN GPON OIDs ────────────────────────────────────────────────────────
ZTE_ONU_OPER_STATE = '1.3.6.1.4.1.3902.1015.1010.1.1.1.5'   # 1=online 2=offline
ZTE_ONU_SERIAL_NUM = '1.3.6.1.4.1.3902.1015.1010.1.1.1.6'
ZTE_ONU_RX_POWER   = '1.3.6.1.4.1.3902.1015.1010.2.1.1.4'   # unit: 0.01 dBm
ZTE_ONU_TX_POWER   = '1.3.6.1.4.1.3902.1015.1010.2.1.1.5'   # unit: 0.01 dBm
ZTE_ONU_OLT_RX     = '1.3.6.1.4.1.3902.1015.1010.2.1.1.6'   # unit: 0.01 dBm

# ── Huawei MA56xx/MA58xx GPON OIDs ───────────────────────────────────────────
HW_ONU_RUN_STATE   = '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.15'  # 1=online 5=offline
HW_ONU_SERIAL_NUM  = '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.2'
HW_ONU_RX_POWER    = '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.4'   # unit: 0.01 dBm
HW_ONU_TX_POWER    = '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.3'   # unit: 0.01 dBm


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine from sync Django code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _decode_serial(value) -> str:
    """
    Decode an SNMP OctetString serial number to a printable string.
    Vendors encode as 4 ASCII chars + 4 raw bytes: e.g. HWTC + \\x00\\xaa\\xbb\\x12
    → 'HWTC00AABB12'
    """
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        # puresnmp may return hex string like '0x4857544300AABB12'
        if value.startswith('0x'):
            try:
                raw = bytes.fromhex(value[2:])
            except ValueError:
                return value
        else:
            return value
    else:
        return str(value)

    if len(raw) == 8:
        prefix = raw[:4].decode('ascii', errors='replace')
        suffix = raw[4:].hex().upper()
        return prefix + suffix
    try:
        return raw.decode('ascii', errors='replace').strip('\x00')
    except Exception:
        return raw.hex().upper()


def _to_power(value) -> float:
    """Convert raw 0.01 dBm integer to float dBm."""
    try:
        return round(int(value) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _index_suffix(full_oid: str, base_oid: str) -> str:
    return full_oid[len(base_oid):].lstrip('.')


def _parse_index(suffix: str) -> tuple[int, int, int, int] | None:
    parts = suffix.split('.')
    try:
        if len(parts) == 4:
            b, s, p, o = (int(x) for x in parts)
            return b, s, p, o
        if len(parts) == 3:
            s, p, o = (int(x) for x in parts)
            return 1, s, p, o
    except ValueError:
        pass
    return None


# ── Low-level SNMP calls ──────────────────────────────────────────────────────

def _make_client(host: str, community: str, port: int = 161, timeout: int = 5):
    from functools import partial
    from puresnmp import Client, V2C, PyWrapper
    from puresnmp.transport import send_udp
    sender = partial(send_udp, timeout=timeout, retries=2)
    return PyWrapper(Client(host, V2C(community), port=port, sender=sender))


async def _async_get(host: str, community: str, oids: list[str],
                     port: int = 161, timeout: int = 5) -> dict[str, any]:
    client = _make_client(host, community, port, timeout)
    results = {}
    for oid in oids:
        try:
            results[oid] = await client.get(oid)
        except Exception as exc:
            logger.debug('SNMP GET %s [%s]: %s', host, oid, exc)
    return results


async def _async_walk(host: str, community: str, base_oid: str,
                      port: int = 161, timeout: int = 5) -> dict[str, any]:
    client = _make_client(host, community, port, timeout)
    results = {}
    async for varbind in client.walk(base_oid):
        results[str(varbind.oid)] = varbind.value
    logger.info('SNMP WALK %s:%s OID %s → %d rows', host, port, base_oid, len(results))
    return results


def _snmp_get(host: str, community: str, oids: list[str],
              port: int = 161, timeout: int = 5) -> dict[str, any]:
    return _run(_async_get(host, community, oids, port, timeout))


def _snmp_walk(host: str, community: str, base_oid: str,
               port: int = 161, timeout: int = 5) -> dict[str, any]:
    return _run(_async_walk(host, community, base_oid, port, timeout))


# ── Public API ────────────────────────────────────────────────────────────────

def check_olt_status_snmp(olt) -> dict:
    """
    Lightweight SNMP reachability check.
    Returns {connected, firmware, uptime_seconds, latency_ms, error}.
    """
    import time
    t0 = time.monotonic()
    result = get_olt_stats_snmp(olt)
    return {
        'connected':      result['connected'],
        'firmware':       result.get('firmware', ''),
        'uptime_seconds': result.get('uptime_seconds', 0),
        'latency_ms':     int((time.monotonic() - t0) * 1000),
        'error':          result.get('error', ''),
    }


def get_olt_stats_snmp(olt) -> dict:
    """
    Fetch sysDescr and sysUpTime via standard MIB-II OIDs.
    Returns {connected, firmware, uptime_seconds, error}.
    """
    host      = str(olt.ip_address)
    community = olt.snmp_community or 'public'
    port      = getattr(olt, 'snmp_port', 161) or 161
    try:
        data = _snmp_get(host, community, [OID_SYS_DESCR, OID_SYS_UPTIME], port=port)
        if not data:
            return {'connected': False, 'firmware': '', 'uptime_seconds': 0,
                    'error': 'No SNMP response — check community string and that SNMP is enabled.'}
        firmware   = str(data.get(OID_SYS_DESCR, ''))
        uptime_raw = data.get(OID_SYS_UPTIME, 0)
        try:
            uptime_seconds = int(str(uptime_raw).split(' ')[0]) // 100
        except (ValueError, IndexError):
            uptime_seconds = 0
        return {'connected': True, 'firmware': firmware[:100], 'uptime_seconds': uptime_seconds, 'error': ''}
    except Exception as exc:
        logger.error('SNMP stats OLT %s: %s', host, exc)
        return {'connected': False, 'firmware': '', 'uptime_seconds': 0, 'error': str(exc)}


def get_onu_list_snmp(olt) -> list[dict]:
    """
    Walk the vendor GPON ONU table.
    Returns list of {board, port, ont_id, status, serial_number, rx_power, tx_power, olt_rx_power}.
    """
    host      = str(olt.ip_address)
    community = olt.snmp_community or 'public'
    port      = getattr(olt, 'snmp_port', 161) or 161
    vendor    = olt.vendor.upper()
    try:
        if vendor == 'ZTE':
            return _get_onu_list_zte(host, community, port)
        elif vendor == 'HUAWEI':
            return _get_onu_list_huawei(host, community, port)
        else:
            logger.warning('SNMP ONU list: unsupported vendor %s', vendor)
            return []
    except Exception as exc:
        logger.error('SNMP ONU list OLT %s: %s', host, exc)
        return []


def _get_onu_list_zte(host: str, community: str, port: int = 161) -> list[dict]:
    state_table  = _snmp_walk(host, community, ZTE_ONU_OPER_STATE, port=port)
    serial_table = _snmp_walk(host, community, ZTE_ONU_SERIAL_NUM, port=port)
    rx_table     = _snmp_walk(host, community, ZTE_ONU_RX_POWER,   port=port)
    tx_table     = _snmp_walk(host, community, ZTE_ONU_TX_POWER,   port=port)
    olt_rx_table = _snmp_walk(host, community, ZTE_ONU_OLT_RX,     port=port)

    results = []
    for full_oid, state_val in state_table.items():
        suffix = _index_suffix(full_oid, ZTE_ONU_OPER_STATE)
        idx    = _parse_index(suffix)
        if not idx:
            continue
        board, slot, pon_port, onu_id = idx
        status = 'online' if str(state_val).strip() in ('1', 'online') else 'offline'
        results.append({
            'board':         board,
            'port':          pon_port,
            'ont_id':        onu_id,
            'status':        status,
            'serial_number': _decode_serial(serial_table.get(f'{ZTE_ONU_SERIAL_NUM}.{suffix}', b'')),
            'rx_power':      _to_power(rx_table.get(f'{ZTE_ONU_RX_POWER}.{suffix}', 0)),
            'tx_power':      _to_power(tx_table.get(f'{ZTE_ONU_TX_POWER}.{suffix}', 0)),
            'olt_rx_power':  _to_power(olt_rx_table.get(f'{ZTE_ONU_OLT_RX}.{suffix}', 0)),
        })
    return results


def _get_onu_list_huawei(host: str, community: str, port: int = 161) -> list[dict]:
    state_table  = _snmp_walk(host, community, HW_ONU_RUN_STATE,  port=port)
    serial_table = _snmp_walk(host, community, HW_ONU_SERIAL_NUM, port=port)
    rx_table     = _snmp_walk(host, community, HW_ONU_RX_POWER,   port=port)
    tx_table     = _snmp_walk(host, community, HW_ONU_TX_POWER,   port=port)

    results = []
    for full_oid, state_val in state_table.items():
        suffix = _index_suffix(full_oid, HW_ONU_RUN_STATE)
        idx    = _parse_index(suffix)
        if not idx:
            continue
        board, slot, pon_port, onu_id = idx
        status = 'online' if str(state_val).strip() == '1' else 'offline'
        results.append({
            'board':         board,
            'port':          pon_port,
            'ont_id':        onu_id,
            'status':        status,
            'serial_number': _decode_serial(serial_table.get(f'{HW_ONU_SERIAL_NUM}.{suffix}', b'')),
            'rx_power':      _to_power(rx_table.get(f'{HW_ONU_RX_POWER}.{suffix}', 0)),
            'tx_power':      _to_power(tx_table.get(f'{HW_ONU_TX_POWER}.{suffix}', 0)),
            'olt_rx_power':  0.0,
        })
    return results
