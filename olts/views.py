import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from .models import OLT, PONPort, DiscoveredONT
from .forms import OLTForm, PONPortForm
from monitoring.models import OLTMetrics, Event
from core.utils import operator_required, admin_required

logger = logging.getLogger('olts.views')


@login_required
def olt_list(request):
    from django.contrib.auth.models import User as AuthUser
    search      = request.GET.get('q', '')
    vendor      = request.GET.get('vendor', '')
    status      = request.GET.get('status', '')
    user_filter = request.GET.get('user', '')

    olts = _olt_qs(request.user)
    if search:
        olts = olts.filter(
            Q(name__icontains=search) |
            Q(ip_address__icontains=search) |
            Q(location__icontains=search)
        )
    if vendor:
        olts = olts.filter(vendor=vendor)
    if status:
        olts = olts.filter(status=status)
    if user_filter and request.user.is_superuser:
        olts = olts.filter(owner__id=user_filter)

    all_users = AuthUser.objects.all().order_by('username') if request.user.is_superuser else []

    return render(request, 'olts/list.html', {
        'olts': olts,
        'search': search,
        'vendor_filter': vendor,
        'status_filter': status,
        'user_filter': user_filter,
        'all_users': all_users,
    })


def _olt_qs(user=None):
    qs = OLT.objects.filter(is_deleted=False)
    if user and not user.is_superuser:
        qs = qs.filter(owner=user)
    return qs.annotate(
        ont_count=Count('onts'),
        online_ont_count=Count('onts', filter=Q(onts__status='online')),
        offline_ont_count=Count(
            'onts',
            filter=Q(onts__status__in=['offline', 'los', 'power_failure', 'fiber_cut'])
        ),
    )


@login_required
def olt_detail(request, pk):
    olt = get_object_or_404(_olt_qs(request.user), pk=pk)
    pon_ports = olt.pon_ports.annotate(
        online_count=Count('onts', filter=Q(onts__status='online')),
        offline_count=Count('onts', filter=Q(onts__status__in=['offline', 'los', 'power_failure', 'fiber_cut', 'degraded'])),
        total_count=Count('onts'),
    ).order_by('board', 'port')
    recent_events = Event.objects.filter(olt=olt).select_related('ont').order_by('-timestamp')[:20]
    from onts.models import ONTProfile
    return render(request, 'olts/detail.html', {
        'olt': olt,
        'pon_ports': pon_ports,
        'recent_events': recent_events,
        'ont_profiles': ONTProfile.objects.all(),
    })


@login_required
@operator_required
def olt_create(request):
    if not request.user.profile.can_add_olt:
        messages.error(request,
            f'OLT quota reached ({request.user.profile.olt_used}/{request.user.profile.olt_quota}). '
            f'Contact your administrator to increase your quota.'
        )
        return redirect('olt_list')

    if request.method == 'POST':
        form = OLTForm(request.POST)
        if form.is_valid():
            olt = form.save(commit=False)
            olt.status = 'unknown'
            olt.owner = request.user
            olt.save()

            from django.conf import settings as dj_settings
            if dj_settings.USE_CELERY:
                task_id = None
                try:
                    from .tasks import setup_new_olt
                    task = setup_new_olt.delay(olt.pk)
                    task_id = task.id
                except Exception:
                    pass
                messages.info(request, f'OLT "{olt.name}" saved. Testing connection and syncing in the background…')
                if task_id:
                    return redirect(f'/olts/{olt.pk}/?setup_task={task_id}')
            else:
                from .snmp_service import check_olt_status_snmp
                from .ssh_service import sync_olt_from_device_sync
                result = check_olt_status_snmp(olt)
                olt.status = 'online' if result['connected'] else 'offline'
                if result.get('firmware'):
                    olt.firmware_version = result['firmware']
                if result.get('uptime_seconds'):
                    olt.uptime = result['uptime_seconds']
                olt.save(update_fields=['status', 'firmware_version', 'uptime'])
                if result['connected']:
                    sync = sync_olt_from_device_sync(olt)
                    messages.success(request,
                        f'OLT "{olt.name}" reachable via SNMP. '
                        f'Found {sync["ports_found"]} port(s) and {sync["onts_found"]} ONT(s).'
                        if sync['ports_found'] or sync['onts_found'] else
                        f'OLT "{olt.name}" reachable via SNMP. No ONTs found yet — use Sync from Device.'
                    )
                else:
                    messages.warning(request,
                        f'OLT "{olt.name}" saved but SNMP check failed: {result["error"]}'
                    )

            return redirect('olt_setup_commands', pk=olt.pk)
    else:
        form = OLTForm()
    return render(request, 'olts/form.html', {'form': form, 'action': 'Add OLT'})


@login_required
def olt_snmp_live(request, pk):
    """Return live ONU list from SNMP, grouped by PON port."""
    olt = get_object_or_404(OLT, pk=pk, is_deleted=False)
    logger.info('SNMP Refresh → OLT "%s" (%s)', olt.name, olt.ip_address)
    from .snmp_service import get_onu_list_snmp
    try:
        onts = get_onu_list_snmp(olt)
        logger.info('SNMP Refresh → found %d ONUs (online: %d, offline: %d)',
                    len(onts),
                    sum(1 for o in onts if o['status'] == 'online'),
                    sum(1 for o in onts if o['status'] != 'online'))
    except Exception as exc:
        logger.error('SNMP Refresh → OLT "%s" error: %s', olt.name, exc)
        return JsonResponse({'error': str(exc), 'ports': []})

    port_map = {}
    for o in onts:
        key = (o['board'], o['port'])
        if key not in port_map:
            port_map[key] = {'board': o['board'], 'port': o['port'], 'onts': []}
        port_map[key]['onts'].append({
            'ont_id':        o['ont_id'],
            'status':        o['status'],
            'serial_number': o['serial_number'],
            'rx_power':      o['rx_power'],
            'tx_power':      o['tx_power'],
            'olt_rx_power':  o.get('olt_rx_power', 0),
        })

    ports = sorted(port_map.values(), key=lambda p: (p['board'], p['port']))
    return JsonResponse({
        'total_ports':  len(ports),
        'total_onts':   len(onts),
        'online_onts':  sum(1 for o in onts if o['status'] == 'online'),
        'offline_onts': sum(1 for o in onts if o['status'] != 'online'),
        'ports': ports,
        'error': '',
    })


@login_required
def pon_snmp_live(request, olt_pk, pon_pk):
    """Return live ONU list from SNMP for a single PON port."""
    olt      = get_object_or_404(OLT, pk=olt_pk, is_deleted=False)
    pon_port = get_object_or_404(PONPort, pk=pon_pk, olt=olt)
    from .snmp_service import get_onu_list_snmp
    try:
        all_onts = get_onu_list_snmp(olt)
    except Exception as exc:
        return JsonResponse({'error': str(exc), 'onts': []})

    onts = [o for o in all_onts
            if o['board'] == pon_port.board and o['port'] == pon_port.port]
    return JsonResponse({
        'board':   pon_port.board,
        'port':    pon_port.port,
        'total':   len(onts),
        'online':  sum(1 for o in onts if o['status'] == 'online'),
        'offline': sum(1 for o in onts if o['status'] != 'online'),
        'onts':    onts,
        'error':   '',
    })


@login_required
def olt_snmp_unregistered(request, pk):
    """Return ONUs visible via SNMP that have no matching registered ONT in the DB."""
    olt = get_object_or_404(OLT, pk=pk, is_deleted=False)
    logger.info('SNMP Scan → OLT "%s" (%s) scanning for unregistered ONUs', olt.name, olt.ip_address)
    from .snmp_service import get_onu_list_snmp
    from onts.models import ONT

    try:
        snmp_onts = get_onu_list_snmp(olt)
        logger.info('SNMP Scan → got %d total ONUs from OLT', len(snmp_onts))
    except Exception as exc:
        logger.error('SNMP Scan → OLT "%s" error: %s', olt.name, exc)
        return JsonResponse({'error': str(exc), 'total': 0, 'ports': []})

    # Build a set of registered (board, port, ont_id) tuples and known serials
    registered = ONT.objects.filter(olt=olt).values_list(
        'pon_port__board', 'pon_port__port', 'ont_id', 'serial_number'
    )
    reg_keys    = {(b, p, oid) for b, p, oid, _ in registered}
    reg_serials = {s.upper() for _, _, _, s in registered if s}

    unregistered = []
    for o in snmp_onts:
        key = (o['board'], o['port'], o['ont_id'])
        serial = (o.get('serial_number') or '').upper()
        if key not in reg_keys and (not serial or serial not in reg_serials):
            unregistered.append(o)

    # Group by port for the frontend
    port_map = {}
    for o in unregistered:
        key = (o['board'], o['port'])
        if key not in port_map:
            pon = olt.pon_ports.filter(board=o['board'], port=o['port']).first()
            port_map[key] = {
                'board':      o['board'],
                'port':       o['port'],
                'port_id':    pon.pk if pon else None,
                'port_label': pon.port_label if pon else f"Board {o['board']} / Port {o['port']}",
                'onts':       [],
            }
        port_map[key]['onts'].append({
            'ont_id':        o['ont_id'],
            'serial':        o.get('serial_number', ''),
            'status':        o['status'],
            'rx_power':      o.get('rx_power', 0),
        })

    ports = sorted(port_map.values(), key=lambda p: (p['board'], p['port']))
    logger.info('SNMP Scan → %d unregistered ONUs found', len(unregistered))
    return JsonResponse({'total': len(unregistered), 'ports': ports, 'error': ''})


@login_required
def olt_setup_commands(request, pk):
    olt = get_object_or_404(OLT, pk=pk, is_deleted=False)
    return render(request, 'olts/setup_commands.html', {'olt': olt})


@login_required
@operator_required
def olt_edit(request, pk):
    olt = get_object_or_404(OLT, pk=pk, is_deleted=False) if request.user.is_superuser else get_object_or_404(OLT, pk=pk, owner=request.user, is_deleted=False)
    if request.method == 'POST':
        form = OLTForm(request.POST, instance=olt)
        if form.is_valid():
            form.save()
            messages.success(request, f'OLT "{olt.name}" updated.')
            return redirect('olt_detail', pk=olt.pk)
    else:
        form = OLTForm(instance=olt)
    return render(request, 'olts/form.html', {'form': form, 'olt': olt, 'action': 'Edit OLT'})


@login_required
def olt_delete(request, pk):
    olt = get_object_or_404(OLT, pk=pk, is_deleted=False) if request.user.is_superuser else get_object_or_404(OLT, pk=pk, owner=request.user, is_deleted=False)
    if request.method == 'POST':
        olt.soft_delete()
        messages.success(request, f'OLT "{olt.name}" deleted.')
        return redirect('olt_list')
    return render(request, 'olts/confirm_delete.html', {'olt': olt})


@login_required
def olt_metrics_data(request, pk):
    olt = get_object_or_404(OLT, pk=pk)
    metrics = OLTMetrics.objects.filter(olt=olt).order_by('timestamp')[:48]
    return JsonResponse({
        'labels': [m.timestamp.strftime('%H:%M') for m in metrics],
        'cpu': [m.cpu_usage for m in metrics],
        'memory': [m.memory_usage for m in metrics],
        'temperature': [m.temperature for m in metrics],
    })


@login_required
@operator_required
def olt_refresh(request, pk):
    """Trigger an SSH poll for this OLT. Returns immediately with a task ID."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=405)

    olt = get_object_or_404(OLT, pk=pk)

    from django.conf import settings as dj_settings
    if dj_settings.USE_CELERY:
        try:
            from .tasks import poll_olt_stats
            task = poll_olt_stats.delay(olt.pk)
            return JsonResponse({'status': 'queued', 'task_id': task.id})
        except Exception:
            pass

    from .ssh_service import poll_olt_stats_sync
    result = poll_olt_stats_sync(olt)
    return JsonResponse({'status': 'ok', **result})


@login_required
@operator_required
def olt_test_connection(request, pk):
    """Test SSH connectivity to a saved OLT and return results as JSON.
    Updates OLT status to 'online' on success, 'offline' on failure."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=405)

    olt = get_object_or_404(OLT, pk=pk)
    from .ssh_service import test_connection
    result = test_connection(olt)

    new_status = 'online' if result.get('connected') else 'offline'
    if olt.status != new_status:
        OLT.objects.filter(pk=pk).update(status=new_status)
        result['status_updated'] = True
        result['new_status'] = new_status

    return JsonResponse(result)


@login_required
@operator_required
def olt_test_connection_raw(request):
    """
    Test SSH connectivity using raw form fields (no saved OLT needed).
    Used by the Add OLT form before the device is saved.
    POST body: ip_address, ssh_port, username, password, vendor
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    ip       = request.POST.get('ip_address', '').strip()
    port     = int(request.POST.get('telnet_port', 23))
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    vendor   = request.POST.get('vendor', 'ZTE').strip().upper()

    if not ip or not username or not password:
        return JsonResponse({'connected': False, 'error': 'IP, username and password are required.'})

    from .ssh_service import _test_telnet_raw
    result = _test_telnet_raw(host=ip, port=port, username=username, password=password)
    return JsonResponse({
        'connected': result['connected'],
        'vendor': vendor,
        'firmware': '',
        'latency_ms': result['latency_ms'],
        'error': result['error'],
    })


@login_required
@operator_required
def sync_olt_device(request, pk):
    """Sync PON ports and ONTs from the live OLT device via SSH."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    olt = get_object_or_404(OLT, pk=pk)
    from .ssh_service import sync_olt_from_device_sync
    result = sync_olt_from_device_sync(olt)

    if not result['error']:
        OLT.objects.filter(pk=pk).update(status='online')
        result['status'] = 'ok'
    else:
        OLT.objects.filter(pk=pk).update(status='offline')
        result['status'] = 'error'

    return JsonResponse(result)


@login_required
@operator_required
def scan_olt_all_ports(request, pk):
    """
    Scan all PON ports on an OLT for unregistered ONTs.
    Returns JSON grouped by port: [{port_id, port_label, onts: [...]}]
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    olt = get_object_or_404(OLT, pk=pk)
    from .ssh_service import scan_all_uncfg_sync

    found = scan_all_uncfg_sync(olt)

    # Group by port
    port_map = {}
    for entry in found:
        key = (entry['board'], entry['port'])
        if key not in port_map:
            port_map[key] = []
        port_map[key].append(entry)

    results = []
    for (board, port_num), onts in sorted(port_map.items()):
        pon_port = olt.pon_ports.filter(board=board, port=port_num).first()
        results.append({
            'port_id':    pon_port.pk if pon_port else None,
            'port_label': pon_port.port_label if pon_port else f'Board {board} / Port {port_num}',
            'board':      board,
            'port':       port_num,
            'onts':       onts,
        })

    total = sum(len(r['onts']) for r in results)
    return JsonResponse({'total': total, 'ports': results})


@login_required
@operator_required
def scan_pon_port(request, olt_pk, pon_pk):
    """
    Trigger SSH auto-discovery on a PON port and return discovered
    unregistered ONTs as JSON.  POST only.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    olt = get_object_or_404(OLT, pk=olt_pk)
    pon_port = get_object_or_404(PONPort, pk=pon_pk, olt=olt)

    from .ssh_service import discover_unregistered_onts_sync
    found = discover_unregistered_onts_sync(olt, pon_port)

    return JsonResponse({
        'found': len(found),
        'onts': found,
    })


@login_required
def pon_detail(request, olt_pk, pon_pk):
    olt = get_object_or_404(_olt_qs(request.user), pk=olt_pk)
    pon_port = get_object_or_404(PONPort, pk=pon_pk, olt=olt)
    registered_onts = list(pon_port.onts.all().order_by('ont_id'))

    ont_map = {ont.ont_id: ont for ont in registered_onts}
    registered_ids = set(ont_map.keys())
    max_slot = max(pon_port.max_onts, max(registered_ids, default=0))

    slots = []
    for i in range(1, max_slot + 1):
        if i in ont_map:
            slots.append({'slot_id': i, 'ont': ont_map[i], 'registered': True})
        else:
            slots.append({'slot_id': i, 'ont': None, 'registered': False})

    online_count = sum(1 for ont in registered_onts if ont.status == 'online')
    offline_count = sum(1 for ont in registered_onts if ont.status in ('offline', 'los', 'power_failure', 'fiber_cut', 'degraded'))
    provisioning_count = sum(1 for ont in registered_onts if ont.status == 'provisioning')
    unregistered_count = pon_port.max_onts - len(registered_onts)

    discovered = DiscoveredONT.objects.filter(pon_port=pon_port)

    return render(request, 'olts/pon_detail.html', {
        'olt': olt,
        'pon_port': pon_port,
        'registered_onts': registered_onts,
        'slots': slots,
        'online_count': online_count,
        'offline_count': offline_count,
        'provisioning_count': provisioning_count,
        'unregistered_count': unregistered_count,
        'registered_count': len(registered_onts),
        'discovered_onts': discovered,
    })


@login_required
def super_admin_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('olt_list')

    from django.contrib.auth.models import User
    from onts.models import ONT

    all_olts = _olt_qs().select_related('owner')
    all_users = User.objects.filter(is_active=True).select_related('profile').order_by('date_joined')

    user_stats = []
    for u in all_users:
        user_olts = all_olts.filter(owner=u)
        ont_qs = ONT.objects.filter(olt__owner=u, olt__is_deleted=False)
        user_stats.append({
            'user': u,
            'olt_count': user_olts.count(),
            'ont_count': ont_qs.count(),
            'online_count': ont_qs.filter(status='online').count(),
            'olts': user_olts[:5],
        })

    total_olts   = all_olts.count()
    total_onts   = ONT.objects.filter(olt__is_deleted=False).count()
    online_onts  = ONT.objects.filter(olt__is_deleted=False, status='online').count()
    offline_onts = ONT.objects.filter(olt__is_deleted=False, status__in=['offline','los','power_failure','fiber_cut']).count()

    return render(request, 'olts/super_admin_dashboard.html', {
        'all_olts': all_olts,
        'user_stats': user_stats,
        'total_users': all_users.count(),
        'total_olts': total_olts,
        'total_onts': total_onts,
        'online_onts': online_onts,
        'offline_onts': offline_onts,
    })


@login_required
def olt_diag(request, pk):
    """
    Superadmin-only: run safe read-only commands on the OLT and return raw output.
    Helps debug parsing issues without touching device config.
    POST with ?cmd=<command_key>  e.g. ?cmd=port_list  or ?cmd=raw&raw=show+version
    """
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Superadmin only'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    olt = get_object_or_404(OLT, pk=pk)
    cmd_key = request.POST.get('cmd', '').strip()
    raw_cmd = request.POST.get('raw', '').strip()

    # Whitelist of safe read-only commands
    SAFE_KEYS = {'version', 'cpu', 'memory', 'temperature', 'port_list',
                 'ont_list', 'ont_detail', 'uncfg_list', 'uncfg_all', 'optical'}

    from .ssh_service import _VENDOR_COMMANDS, TelnetSession, TELNET_TIMEOUT
    import re as _re

    cmds = _VENDOR_COMMANDS.get(olt.vendor, {})

    # Build the actual command string
    if raw_cmd:
        # Only allow show/display commands — block anything that could change config
        if not _re.match(r'^\s*(show|display)\s+', raw_cmd, _re.I):
            return JsonResponse({'error': 'Only show/display commands allowed.'})
        cmd = raw_cmd
    elif cmd_key in SAFE_KEYS:
        template = cmds.get(cmd_key, '')
        if not template:
            return JsonResponse({'error': f'No command for key {cmd_key} on {olt.vendor}'})
        board  = int(request.POST.get('board', 1))
        port   = int(request.POST.get('port', 1))
        port_b = int(request.POST.get('port_b', 1))
        ont_id = int(request.POST.get('ont_id', 1))
        try:
            cmd = template.format(board=board, port_b=port_b, port=port, ont_id=ont_id)
        except KeyError:
            cmd = template
    else:
        return JsonResponse({'error': f'Unknown cmd key: {cmd_key}. Use one of: {sorted(SAFE_KEYS)}'})

    try:
        session = TelnetSession(
            host=str(olt.ip_address),
            port=olt.telnet_port,
            username=olt.username,
            password=olt.password,
            timeout=TELNET_TIMEOUT,
        )
        output = session.send_command(cmd, timeout=TELNET_TIMEOUT)
        session.close()
        return JsonResponse({'cmd': cmd, 'output': output, 'vendor': olt.vendor})
    except Exception as exc:
        return JsonResponse({'cmd': cmd, 'error': str(exc), 'output': ''})


@login_required
def olt_task_status(request, task_id):
    """Poll Celery task result."""
    try:
        from celery.result import AsyncResult
        res = AsyncResult(task_id)
        if res.ready():
            return JsonResponse({'status': 'done', 'result': res.result})
        return JsonResponse({'status': 'pending'})
    except Exception:
        return JsonResponse({'status': 'unavailable'})
