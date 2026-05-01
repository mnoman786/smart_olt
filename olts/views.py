from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from .models import OLT, PONPort
from .forms import OLTForm, PONPortForm
from monitoring.models import OLTMetrics, Event
from core.utils import operator_required, admin_required


@login_required
def olt_list(request):
    search = request.GET.get('q', '')
    vendor = request.GET.get('vendor', '')
    status = request.GET.get('status', '')

    olts = OLT.objects.annotate(
        ont_count=Count('onts'),
        online_ont_count=Count('onts', filter=Q(onts__status='online')),
        offline_ont_count=Count(
            'onts',
            filter=Q(onts__status__in=['offline', 'los', 'power_failure', 'fiber_cut'])
        ),
    )
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


@login_required
def olt_detail(request, pk):
    olt = get_object_or_404(OLT, pk=pk)
    pon_ports = olt.pon_ports.annotate(ont_count=Count('onts'))
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
