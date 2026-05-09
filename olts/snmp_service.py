"""
SNMP service for OLT monitoring.

Auto-detects pysnmp API version:
  - pysnmp 6.x (official)     → pysnmp.hlapi.asyncio        (coroutine-based)
  - pysnmp-lextudio 6.x       → pysnmp.hlapi.v3arch.asyncio (coroutine-based)
  - pysnmp 4.x / 5.x          → pysnmp.hlapi                (sync generator-based)

Install:
    pip install "pysnmp>=6.2.0,<7.0.0"
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import logging
import sys

# SelectorEventLoop handles UDP cleanly on Windows; ProactorEventLoop leaks sockets.
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


# ── pysnmp version detection ──────────────────────────────────────────────────

def _load_pysnmp():
    """
    Return (SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
            ObjectType, ObjectIdentity, getCmd, nextCmd, is_async).

    Priority order:
      1. pysnmp 6.x unified (v3arch asyncio path — current recommended)
      2. pysnmp-lextudio / pysnmp 6.x legacy asyncio path
      3. pysnmp 4.x / 5.x synchronous generator API
    """
    # pysnmp 6.x official — hlapi.asyncio
    try:
        from pysnmp.hlapi.asyncio import (        # noqa: PLC0415
            SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
            ObjectType, ObjectIdentity, getCmd, nextCmd,
        )
        logger.debug('pysnmp: hlapi.asyncio API (v6.x official)')
        return (SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
                ObjectType, ObjectIdentity, getCmd, nextCmd, True)
    except ImportError:
        pass

    # pysnmp-lextudio 6.x — v3arch.asyncio path
    try:
        from pysnmp.hlapi.v3arch.asyncio import (  # noqa: PLC0415
            SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
            ObjectType, ObjectIdentity, getCmd, nextCmd,
        )
        logger.debug('pysnmp: v3arch asyncio API (v6.x lextudio)')
        return (SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
                ObjectType, ObjectIdentity, getCmd, nextCmd, True)
    except ImportError:
        pass

    # pysnmp 4.x / 5.x — synchronous generator API
    try:
        from pysnmp.hlapi import (                # noqa: PLC0415
            SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
            ObjectType, ObjectIdentity, getCmd, nextCmd,
        )
        logger.debug('pysnmp: sync API (v4.x/5.x)')
        return (SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
                ObjectType, ObjectIdentity, getCmd, nextCmd, False)
    except ImportError:
        pass

    raise ImportError(
        'pysnmp not installed or version incompatible.\n'
        'Run:  pip install pysnmp'
    )


(
    _SnmpEngine, _CommunityData, _UdpTransportTarget, _ContextData,
    _ObjectType, _ObjectIdentity, _getCmd, _nextCmd, _PYSNMP_ASYNC,
) = _load_pysnmp()


# ── Async execution helper ────────────────────────────────────────────────────

def _run(coro):
    """Execute a coroutine from synchronous Django / Celery code."""
    try:
        asyncio.get_running_loop()
        # Inside an already-running loop (ASGI, etc.) — offload to a thread.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_serial(value) -> str:
    """
    Decode an SNMP OctetString serial number to a printable string.
    Vendors encode as 4 ASCII chars + 4 raw bytes → e.g. 'HWTC00AABB12'.
    Accepts pysnmp OctetString objects, plain bytes, or strings.
    """
    if isinstance(value, bytes):
        raw = value
    elif hasattr(value, '__bytes__'):
        try:
            raw = bytes(value)
        except Exception:
            raw = str(value).encode('ascii', errors='replace')
    elif isinstance(value, str):
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
        return raw[:4].decode('ascii', errors='replace') + raw[4:].hex().upper()
    try:
        return raw.decode('ascii', errors='replace').strip('\x00')
    except Exception:
        return raw.hex().upper()


def _to_power(value) -> float:
    """Convert raw 0.01 dBm integer (or pysnmp Integer) to float dBm."""
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


# ── Low-level SNMP — async path (pysnmp 6.x) ─────────────────────────────────

async def _async_get(host: str, community: str, oids: list[str],
                     port: int = 161, timeout: int = 5) -> dict:
    """Fresh SnmpEngine per GET — required for pysnmp 6.x asyncio API."""
    results: dict = {}
    for oid in oids:
        engine = _SnmpEngine()
        try:
            errInd, errSt, errIdx, varBinds = await _getCmd(
                engine,
                _CommunityData(community, mpModel=1),
                _UdpTransportTarget((host, port), timeout=timeout, retries=1),
                _ContextData(),
                _ObjectType(_ObjectIdentity(oid)),
            )
            if not errInd and not errSt:
                for vb in varBinds:
                    val = _vb_val(vb)
                    if val is not None:
                        results[_vb_oid(vb)] = val
            elif errInd:
                logger.debug('SNMP GET %s [%s]: %s', host, oid, errInd)
        except Exception as exc:
            logger.debug('SNMP GET %s [%s]: %s', host, oid, exc)
        finally:
            engine.closeDispatcher()
    return results


async def _async_walk(host: str, community: str, base_oid: str,
                      port: int = 161, timeout: int = 5) -> dict:
    """
    Manual GETNEXT loop compatible with pysnmp-lextudio 6.x.

    In 6.x, nextCmd is a plain coroutine (single GETNEXT step) and the
    asyncio transport inside SnmpEngine is consumed after each await — so
    a fresh SnmpEngine is created for every step.  Cursor advances until
    the returned OID leaves the requested subtree or an error occurs.
    """
    results: dict = {}
    cursor = base_oid

    while True:
        engine = _SnmpEngine()
        try:
            errInd, errSt, errIdx, varBinds = await _nextCmd(
                engine,
                _CommunityData(community, mpModel=1),
                _UdpTransportTarget((host, port), timeout=timeout, retries=0),
                _ContextData(),
                _ObjectType(_ObjectIdentity(cursor)),
            )
        finally:
            engine.closeDispatcher()

        if errInd:
            logger.debug('SNMP WALK %s [%s]: %s', host, base_oid, errInd)
            break
        if errSt:
            logger.debug('SNMP WALK %s [%s]: %s', host, base_oid,
                         errSt.prettyPrint())
            break
        if not varBinds:
            break

        moved = False
        for vb in varBinds:
            oid_str = _vb_oid(vb)
            value   = _vb_val(vb)

            # Detect EndOfMibView / NoSuchObject sentinel values
            if value is None or value.__class__.__name__ in (
                'EndOfMibView', 'NoSuchObject', 'NoSuchInstance'
            ):
                logger.info('SNMP WALK %s:%s OID %s → %d rows (end of MIB)',
                            host, port, base_oid, len(results))
                return results

            # Stop when OID leaves our subtree
            if not oid_str.startswith(base_oid + '.') and oid_str != base_oid:
                logger.info('SNMP WALK %s:%s OID %s → %d rows',
                            host, port, base_oid, len(results))
                return results

            results[oid_str] = value
            cursor = oid_str
            moved  = True

        if not moved:
            break

    logger.info('SNMP WALK %s:%s OID %s → %d rows', host, port, base_oid, len(results))
    return results


# ── Low-level SNMP — sync path (pysnmp 4.x / 5.x) ───────────────────────────

def _sync_get(host: str, community: str, oids: list[str],
              port: int = 161, timeout: int = 5) -> dict:
    results: dict = {}
    engine    = _SnmpEngine()
    auth      = _CommunityData(community, mpModel=1)
    transport = _UdpTransportTarget((host, port), timeout=timeout, retries=1)
    ctx       = _ContextData()
    for oid in oids:
        try:
            errInd, errSt, errIdx, varBinds = next(
                _getCmd(engine, auth, transport, ctx,
                        _ObjectType(_ObjectIdentity(oid)))
            )
            if not errInd and not errSt:
                for vb in varBinds:
                    val = _vb_val(vb)
                    if val is not None:
                        results[_vb_oid(vb)] = val
            elif errInd:
                logger.debug('SNMP GET %s [%s]: %s', host, oid, errInd)
        except Exception as exc:
            logger.debug('SNMP GET %s [%s]: %s', host, oid, exc)
    return results


def _sync_walk(host: str, community: str, base_oid: str,
               port: int = 161, timeout: int = 5) -> dict:
    results: dict = {}
    try:
        for errInd, errSt, errIdx, varBinds in _nextCmd(
            _SnmpEngine(),
            _CommunityData(community, mpModel=1),
            _UdpTransportTarget((host, port), timeout=timeout, retries=0),
            _ContextData(),
            _ObjectType(_ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if errInd:
                logger.debug('SNMP WALK %s [%s]: %s', host, base_oid, errInd)
                break
            if errSt:
                logger.debug('SNMP WALK %s [%s]: %s', host, base_oid,
                             errSt.prettyPrint())
                break
            for vb in varBinds:
                val = _vb_val(vb)
                if val is not None:
                    results[_vb_oid(vb)] = val
    except Exception as exc:
        logger.debug('SNMP WALK %s [%s]: %s', host, base_oid, exc)
    logger.info('SNMP WALK %s:%s OID %s → %d rows', host, port, base_oid, len(results))
    return results


# ── Unified public low-level API ──────────────────────────────────────────────

def _snmp_get(host: str, community: str, oids: list[str],
              port: int = 161, timeout: int = 5) -> dict:
    if _PYSNMP_ASYNC:
        return _run(_async_get(host, community, oids, port, timeout))
    return _sync_get(host, community, oids, port, timeout)


def _snmp_walk(host: str, community: str, base_oid: str,
               port: int = 161, timeout: int = 5) -> dict:
    if _PYSNMP_ASYNC:
        return _run(_async_walk(host, community, base_oid, port, timeout))
    return _sync_walk(host, community, base_oid, port, timeout)


# ── Public API ────────────────────────────────────────────────────────────────

def check_olt_status_snmp(olt) -> dict:
    """
    Lightweight SNMP reachability check.
    Returns {connected, firmware, uptime_seconds, latency_ms, error}.
    """
    import time
    t0     = time.monotonic()
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
            return {
                'connected': False, 'firmware': '', 'uptime_seconds': 0,
                'error': 'No SNMP response — check community string and that SNMP is enabled.',
            }
        firmware_val = data.get(OID_SYS_DESCR, '')
        firmware     = str(firmware_val)[:100] if firmware_val is not None else ''

        uptime_raw = data.get(OID_SYS_UPTIME, 0)
        try:
            uptime_seconds = int(uptime_raw) // 100   # TimeTicks → centiseconds
        except (TypeError, ValueError):
            uptime_seconds = 0

        return {'connected': True, 'firmware': firmware,
                'uptime_seconds': uptime_seconds, 'error': ''}
    except Exception as exc:
        logger.error('SNMP stats OLT %s: %s', host, exc)
        return {'connected': False, 'firmware': '', 'uptime_seconds': 0, 'error': str(exc)}


def get_onu_list_snmp(olt) -> list[dict]:
    """
    Walk the vendor GPON ONU table.
    Returns list of {board, port, ont_id, status, serial_number,
                     rx_power, tx_power, olt_rx_power}.

    Does a sysUpTime GET first so we bail after one timeout if unreachable
    instead of burning 5 × timeout on the subsequent vendor walks.
    """
    host      = str(olt.ip_address)
    community = olt.snmp_community or 'public'
    port      = getattr(olt, 'snmp_port', 161) or 161
    vendor    = olt.vendor.upper()

    probe = _snmp_get(host, community, [OID_SYS_UPTIME], port=port, timeout=5)
    if not probe:
        logger.warning('SNMP ONU list: %s not reachable (no sysUpTime response)', host)
        return []

    try:
        if vendor == 'ZTE':
            return _get_onu_list_zte(host, community, port)
        if vendor == 'HUAWEI':
            return _get_onu_list_huawei(host, community, port)
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
        board, _slot, pon_port, onu_id = idx
        status = 'online' if _safe_int(state_val) == 1 else 'offline'
        results.append({
            'board':         board,
            'port':          pon_port,
            'ont_id':        onu_id,
            'status':        status,
            'serial_number': _decode_serial(
                serial_table.get(f'{ZTE_ONU_SERIAL_NUM}.{suffix}', b'')),
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
        board, _slot, pon_port, onu_id = idx
        status = 'online' if _safe_int(state_val) == 1 else 'offline'
        results.append({
            'board':         board,
            'port':          pon_port,
            'ont_id':        onu_id,
            'status':        status,
            'serial_number': _decode_serial(
                serial_table.get(f'{HW_ONU_SERIAL_NUM}.{suffix}', b'')),
            'rx_power':      _to_power(rx_table.get(f'{HW_ONU_RX_POWER}.{suffix}', 0)),
            'tx_power':      _to_power(tx_table.get(f'{HW_ONU_TX_POWER}.{suffix}', 0)),
            'olt_rx_power':  0.0,
        })
    return results


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _vb_oid(vb) -> str:
    """
    Extract numeric OID string from a varBind regardless of pysnmp version.
    ObjectType in pysnmp is a list subclass: [ObjectName, value].
    Older builds always populate both slots; newer builds may return a
    1-element ObjectType (OID only) in error cases — guard against that.
    """
    try:
        oid_obj = vb[0]
    except (IndexError, TypeError):
        oid_obj = vb
    return oid_obj.prettyPrint() if hasattr(oid_obj, 'prettyPrint') else str(oid_obj)


def _vb_val(vb):
    """
    Extract the value from a varBind.
    Returns None if the varBind has no value slot (1-element ObjectType).
    """
    try:
        return vb[1]
    except (IndexError, TypeError):
        return None
