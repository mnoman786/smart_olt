from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from .models import OLT, PONPort
from .forms import OLTForm, PONPortForm
from monitoring.models import OLTMetrics, Event
import random


@login_required
def olt_list(request):
    search = request.GET.get('q', '')
    vendor = request.GET.get('vendor', '')
    status = request.GET.get('status', '')
    olts = OLT.objects.all()
    if search:
        olts = olts.filter(Q(name__icontains=search) | Q(ip_address__icontains=search) | Q(location__icontains=search))
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
    pon_ports = olt.pon_ports.all()
    recent_events = Event.objects.filter(olt=olt).order_by('-timestamp')[:20]
    metrics = OLTMetrics.objects.filter(olt=olt).order_by('-timestamp')[:48]
    return render(request, 'olts/detail.html', {
        'olt': olt,
        'pon_ports': pon_ports,
        'recent_events': recent_events,
        'metrics': metrics,
    })


@login_required
def olt_create(request):
    if not request.user.profile.is_operator:
        messages.error(request, 'Access denied.')
        return redirect('olt_list')
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
def olt_edit(request, pk):
    if not request.user.profile.is_operator:
        messages.error(request, 'Access denied.')
        return redirect('olt_list')
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
def olt_delete(request, pk):
    if not request.user.profile.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('olt_list')
    olt = get_object_or_404(OLT, pk=pk)
    if request.method == 'POST':
        name = olt.name
        olt.delete()
        messages.success(request, f'OLT "{name}" deleted.')
        return redirect('olt_list')
    return render(request, 'olts/confirm_delete.html', {'olt': olt})


@login_required
def olt_refresh(request, pk):
    if request.method == 'POST':
        olt = get_object_or_404(OLT, pk=pk)
        olt.cpu_usage = round(random.uniform(10, 70), 1)
        olt.memory_usage = round(random.uniform(30, 80), 1)
        olt.temperature = round(random.uniform(35, 55), 1)
        olt.save(update_fields=['cpu_usage', 'memory_usage', 'temperature'])
        return JsonResponse({
            'status': 'ok',
            'cpu_usage': olt.cpu_usage,
            'memory_usage': olt.memory_usage,
            'temperature': olt.temperature,
        })
    return JsonResponse({'status': 'error'}, status=405)


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
