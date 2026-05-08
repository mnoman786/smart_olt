"""
SNMP service for OLT monitoring.

Used for all read/polling operations (ONU list, status, optical power,
CPU, memory). Telnet is kept only for write operations (reboot, provision).

Install:  pip install pysnmp
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# ── Standard MIB-II OIDs (work on every vendor) ──────────────────────────────
OID_SYS_DESCR  = '1.3.6.1.2.1.1.1.0'   # firmware / system description
OID_SYS_UPTIME = '1.3.6.1.2.1.1.3.0'   # uptime in hundredths of a second
OID_SYS_NAME   = '1.3.6.1.2.1.1.5.0'   # hostname

# ── ZTE ZXAN GPON OIDs ────────────────────────────────────────────────────────
# Table index format: board.slot.port.onu_id  (e.g. 1.1.1.1)
ZTE_ONU_OPER_STATE  = '1.3.6.1.4.1.3902.1015.1010.1.1.1.5'   # 1=online 2=offline
ZTE_ONU_SERIAL_NUM  = '1.3.6.1.4.1.3902.1015.1010.1.1.1.6'
ZTE_ONU_TYPE        = '1.3.6.1.4.1.3902.1015.1010.1.1.1.3'
ZTE_ONU_RX_POWER    = '1.3.6.1.4.1.3902.1015.1010.2.1.1.4'   # unit: 0.01 dBm
ZTE_ONU_TX_POWER    = '1.3.6.1.4.1.3902.1015.1010.2.1.1.5'   # unit: 0.01 dBm
ZTE_ONU_OLT_RX      = '1.3.6.1.4.1.3902.1015.1010.2.1.1.6'   # unit: 0.01 dBm

# ── Huawei MA56xx/MA58xx GPON OIDs ───────────────────────────────────────────
# Table index format: slot.port.onu_id
HW_ONU_RUN_STATE    = '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.15'  # 1=online 5=offline
HW_ONU_SERIAL_NUM   = '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.2'
HW_ONU_RX_POWER     = '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.4'   # unit: 0.01 dBm
HW_ONU_TX_POWER     = '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.3'   # unit: 0.01 dBm


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _snmp_get(host: str, community: str, oids: list[str], port: int = 161,
              timeout: int = 5, retries: int = 2) -> dict[str, str]:
    """
    SNMP GET for one or more scalar OIDs.
    Returns {oid: value_str} for each OID.
    """
    from pysnmp.hlapi import (
        getCmd, SnmpEngine, CommunityData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity,
    )
    results = {}
    error_indication, error_status, _, var_binds = next(
        getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),   # mpModel=1 → SNMPv2c
            UdpTransportTarget((host, port), timeout=timeout, retries=retries),
            ContextData(),
            *[ObjectType(ObjectIdentity(oid)) for oid in oids],
        )
    )
    if error_indication or error_status:
        logger.debug('SNMP GET %s: %s %s', host, error_indication, error_status)
        return results
    for var_bind in var_binds:
        oid_str, val = var_bind
        results[str(oid_str)] = str(val)
    return results


def _snmp_walk(host: str, community: str, base_oid: str, port: int = 161,
               timeout: int = 5, retries: int = 2) -> dict[str, str]:
    """
    SNMP WALK under base_oid.
    Returns {full_oid_str: value_str} for every leaf found.
    """
    from pysnmp.hlapi import (
        nextCmd, SnmpEngine, CommunityData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity,
    )
    results = {}
    for error_indication, error_status, _, var_binds in nextCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((host, port), timeout=timeout, retries=retries),
        ContextData(),
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    ):
        if error_indication or error_status:
            break
        for var_bind in var_binds:
            oid_str, val = var_bind
            results[str(oid_str)] = str(val)
    return results


def _index_suffix(full_oid: str, base_oid: str) -> str:
    """Return the index part after the base OID. e.g. '1.1.1.2' """
    return full_oid[len(base_oid):].lstrip('.')


def _parse_index(suffix: str) -> tuple[int, int, int, int] | None:
    """
    Parse a 4-part index (board.slot.port.onu_id) or 3-part (slot.port.onu_id).
    Returns (board, slot, port, onu_id) or None if it can't be parsed.
    """
    parts = suffix.split('.')
    try:
        if len(parts) == 4:
            board, slot, port, onu_id = (int(p) for p in parts)
            return board, slot, port, onu_id
        if len(parts) == 3:
            slot, port, onu_id = (int(p) for p in parts)
            return 1, slot, port, onu_id
    except ValueError:
        pass
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def check_olt_status_snmp(olt) -> dict:
    """
    Lightweight SNMP reachability check — determines online/offline status.
    Fetches sysDescr + sysUpTime via a single SNMP GET.
    Returns {connected, firmware, uptime_seconds, latency_ms, error}.
    """
    import time
    t0 = time.monotonic()
    result = get_olt_stats_snmp(olt)
    latency_ms = int((time.monotonic() - t0) * 1000)
    return {
        'connected':      result['connected'],
        'firmware':       result.get('firmware', ''),
        'uptime_seconds': result.get('uptime_seconds', 0),
        'latency_ms':     latency_ms,
        'error':          result.get('error', ''),
    }


def get_olt_stats_snmp(olt) -> dict:
    """
    Fetch system description and uptime via standard MIB-II OIDs.
    Returns {connected, firmware, uptime_seconds, error}.
    """
    host      = str(olt.ip_address)
    community = olt.snmp_community or 'public'

    try:
        data = _snmp_get(host, community, [OID_SYS_DESCR, OID_SYS_UPTIME])
        if not data:
            return {'connected': False, 'firmware': '', 'uptime_seconds': 0,
                    'error': 'No SNMP response — check community string and that SNMP is enabled.'}

        firmware = data.get(OID_SYS_DESCR, '')
        uptime_raw = data.get(OID_SYS_UPTIME, '0')
        try:
            uptime_seconds = int(uptime_raw.split(' ')[0]) // 100
        except (ValueError, IndexError):
            uptime_seconds = 0

        return {
            'connected':      True,
            'firmware':       firmware[:100],
            'uptime_seconds': uptime_seconds,
            'error':          '',
        }
    except Exception as exc:
        logger.error('SNMP stats OLT %s: %s', host, exc)
        return {'connected': False, 'firmware': '', 'uptime_seconds': 0, 'error': str(exc)}


def get_onu_list_snmp(olt) -> list[dict]:
    """
    Walk the vendor GPON ONU table and return a list of:
      {ont_id, board, port, status, serial_number, rx_power, tx_power, olt_rx_power}

    For ZTE:    index = board.slot.port.onu_id
    For Huawei: index = slot.port.onu_id
    """
    host      = str(olt.ip_address)
    community = olt.snmp_community or 'public'
    vendor    = olt.vendor.upper()

    try:
        if vendor == 'ZTE':
            return _get_onu_list_zte(host, community)
        elif vendor == 'HUAWEI':
            return _get_onu_list_huawei(host, community)
        else:
            logger.warning('SNMP ONU list: unsupported vendor %s', vendor)
            return []
    except Exception as exc:
        logger.error('SNMP ONU list OLT %s: %s', host, exc)
        return []


def _get_onu_list_zte(host: str, community: str) -> list[dict]:
    state_table  = _snmp_walk(host, community, ZTE_ONU_OPER_STATE)
    serial_table = _snmp_walk(host, community, ZTE_ONU_SERIAL_NUM)
    rx_table     = _snmp_walk(host, community, ZTE_ONU_RX_POWER)
    tx_table     = _snmp_walk(host, community, ZTE_ONU_TX_POWER)
    olt_rx_table = _snmp_walk(host, community, ZTE_ONU_OLT_RX)

    results = []
    for full_oid, state_val in state_table.items():
        suffix = _index_suffix(full_oid, ZTE_ONU_OPER_STATE)
        idx    = _parse_index(suffix)
        if not idx:
            continue
        board, slot, port, onu_id = idx

        status = 'online' if state_val.strip() in ('1', 'online') else 'offline'

        def _power(table, base, sfx):
            val = table.get(f'{base}.{sfx}', '0')
            try:
                return round(int(val) / 100.0, 2)
            except ValueError:
                return 0.0

        results.append({
            'board':         board,
            'port':          port,
            'ont_id':        onu_id,
            'status':        status,
            'serial_number': serial_table.get(f'{ZTE_ONU_SERIAL_NUM}.{suffix}', ''),
            'rx_power':      _power(rx_table,     ZTE_ONU_RX_POWER, suffix),
            'tx_power':      _power(tx_table,     ZTE_ONU_TX_POWER, suffix),
            'olt_rx_power':  _power(olt_rx_table, ZTE_ONU_OLT_RX,  suffix),
        })

    return results


def _get_onu_list_huawei(host: str, community: str) -> list[dict]:
    state_table  = _snmp_walk(host, community, HW_ONU_RUN_STATE)
    serial_table = _snmp_walk(host, community, HW_ONU_SERIAL_NUM)
    rx_table     = _snmp_walk(host, community, HW_ONU_RX_POWER)
    tx_table     = _snmp_walk(host, community, HW_ONU_TX_POWER)

    results = []
    for full_oid, state_val in state_table.items():
        suffix = _index_suffix(full_oid, HW_ONU_RUN_STATE)
        idx    = _parse_index(suffix)
        if not idx:
            continue
        board, slot, port, onu_id = idx

        status = 'online' if state_val.strip() == '1' else 'offline'

        def _power(table, base, sfx):
            val = table.get(f'{base}.{sfx}', '0')
            try:
                return round(int(val) / 100.0, 2)
            except ValueError:
                return 0.0

        results.append({
            'board':         board,
            'port':          port,
            'ont_id':        onu_id,
            'status':        status,
            'serial_number': serial_table.get(f'{HW_ONU_SERIAL_NUM}.{suffix}', ''),
            'rx_power':      _power(rx_table, HW_ONU_RX_POWER, suffix),
            'tx_power':      _power(tx_table, HW_ONU_TX_POWER, suffix),
            'olt_rx_power':  0.0,
        })

    return results
