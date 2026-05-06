from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from .models import OLT, PONPort, DiscoveredONT
from .forms import OLTForm, PONPortForm
from monitoring.models import OLTMetrics, Event
from core.utils import operator_required, admin_required


@login_required
def olt_list(request):
    search = request.GET.get('q', '')
    vendor = request.GET.get('vendor', '')
    status = request.GET.get('status', '')

    olts = _olt_qs()
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

    return render(request, 'olts/list.html', {
        'olts': olts,
        'search': search,
        'vendor_filter': vendor,
        'status_filter': status,
    })


def _olt_qs():
    return OLT.objects.annotate(
        ont_count=Count('onts'),
        online_ont_count=Count('onts', filter=Q(onts__status='online')),
        offline_ont_count=Count(
            'onts',
            filter=Q(onts__status__in=['offline', 'los', 'power_failure', 'fiber_cut'])
        ),
    )


@login_required
def olt_detail(request, pk):
    olt = get_object_or_404(_olt_qs(), pk=pk)
    pon_ports = olt.pon_ports.annotate(
        online_count=Count('onts', filter=Q(onts__status='online')),
        offline_count=Count('onts', filter=Q(onts__status__in=['offline', 'los', 'power_failure', 'fiber_cut', 'degraded'])),
        total_count=Count('onts'),
    ).order_by('board', 'port')
    recent_events = Event.objects.filter(olt=olt).select_related('ont').order_by('-timestamp')[:20]
    return render(request, 'olts/detail.html', {
        'olt': olt,
        'pon_ports': pon_ports,
        'recent_events': recent_events,
    })


@login_required
@operator_required
def olt_create(request):
    if request.method == 'POST':
        form = OLTForm(request.POST)
        if form.is_valid():
            olt = form.save()
            messages.success(request, f'OLT "{olt.name}" created successfully.')
            return redirect('olt_detail', pk=olt.pk)
    else:
        form = OLTForm()
    return render(request, 'olts/form.html', {'form': form, 'action': 'Add OLT'})


@login_required
@operator_required
def olt_edit(request, pk):
    olt = get_object_or_404(OLT, pk=pk)
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
@admin_required
def olt_delete(request, pk):
    olt = get_object_or_404(OLT, pk=pk)
    if request.method == 'POST':
        name = olt.name
        olt.delete()
        messages.success(request, f'OLT "{name}" deleted.')
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

    try:
        from .tasks import poll_olt_stats
        task = poll_olt_stats.delay(olt.pk)
        return JsonResponse({'status': 'queued', 'task_id': task.id})
    except Exception:
        # Celery not running — execute synchronously (demo / dev mode)
        from .ssh_service import poll_olt_stats_sync
        result = poll_olt_stats_sync(olt)
        return JsonResponse({'status': 'ok', **result})


@login_required
@operator_required
def olt_test_connection(request, pk):
    """Test SSH connectivity to an OLT and return results as JSON."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=405)

    olt = get_object_or_404(OLT, pk=pk)
    from .ssh_service import test_connection
    result = test_connection(olt)
    return JsonResponse(result)


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
    olt = get_object_or_404(_olt_qs(), pk=olt_pk)
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
