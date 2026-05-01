from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from .models import ONT, ONTProfile
from .forms import ONTForm, ONTProfileForm
from monitoring.models import SignalHistory, TrafficHistory, Event


@login_required
def ont_list(request):
    search = request.GET.get('q', '')
    status = request.GET.get('status', '')
    olt_id = request.GET.get('olt', '')
    technology = request.GET.get('tech', '')

    onts = ONT.objects.select_related('olt', 'pon_port', 'profile').order_by('olt', 'ont_id')
    if search:
        onts = onts.filter(
            Q(name__icontains=search) | Q(serial_number__icontains=search) |
            Q(ip_address__icontains=search) | Q(mac_address__icontains=search)
        )
    if status:
        onts = onts.filter(status=status)
    if olt_id:
        onts = onts.filter(olt_id=olt_id)
    if technology:
        onts = onts.filter(technology=technology)

    from olts.models import OLT
    olts = OLT.objects.all()
    return render(request, 'onts/list.html', {
        'onts': onts,
        'search': search,
        'status_filter': status,
        'olt_filter': olt_id,
        'tech_filter': technology,
        'olts': olts,
        'status_choices': ONT.STATUS_CHOICES,
    })


@login_required
def ont_detail(request, pk):
    ont = get_object_or_404(ONT.objects.select_related('olt', 'pon_port', 'profile'), pk=pk)
    recent_events = Event.objects.filter(ont=ont).order_by('-timestamp')[:20]
    return render(request, 'onts/detail.html', {'ont': ont, 'recent_events': recent_events})


@login_required
def ont_create(request):
    if not request.user.profile.is_operator:
        messages.error(request, 'Access denied.')
        return redirect('ont_list')
    if request.method == 'POST':
        form = ONTForm(request.POST)
        if form.is_valid():
            ont = form.save()
            messages.success(request, f'ONT "{ont.name}" created successfully.')
            return redirect('ont_detail', pk=ont.pk)
    else:
        form = ONTForm()
    return render(request, 'onts/form.html', {'form': form, 'action': 'Add ONT'})


@login_required
def ont_edit(request, pk):
    if not request.user.profile.is_operator:
        messages.error(request, 'Access denied.')
        return redirect('ont_list')
    ont = get_object_or_404(ONT, pk=pk)
    if request.method == 'POST':
        form = ONTForm(request.POST, instance=ont)
        if form.is_valid():
            form.save()
            messages.success(request, f'ONT "{ont.name}" updated.')
            return redirect('ont_detail', pk=ont.pk)
    else:
        form = ONTForm(instance=ont)
    return render(request, 'onts/form.html', {'form': form, 'ont': ont, 'action': 'Edit ONT'})


@login_required
def ont_delete(request, pk):
    if not request.user.profile.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('ont_list')
    ont = get_object_or_404(ONT, pk=pk)
    if request.method == 'POST':
        name = ont.name
        ont.delete()
        messages.success(request, f'ONT "{name}" deleted.')
        return redirect('ont_list')
    return render(request, 'onts/confirm_delete.html', {'ont': ont})


@login_required
def ont_reboot(request, pk):
    if request.method == 'POST':
        ont = get_object_or_404(ONT, pk=pk)
        Event.objects.create(
            type='rebooted', severity='info', olt=ont.olt, ont=ont,
            message=f'ONT {ont.name} ({ont.serial_number}) rebooted by {request.user.username}.'
        )
        return JsonResponse({'status': 'ok', 'message': 'Reboot command sent.'})
    return JsonResponse({'status': 'error'}, status=405)


@login_required
def ont_factory_reset(request, pk):
    if request.method == 'POST':
        ont = get_object_or_404(ONT, pk=pk)
        Event.objects.create(
            type='factory_reset', severity='warning', olt=ont.olt, ont=ont,
            message=f'ONT {ont.name} ({ont.serial_number}) factory reset by {request.user.username}.'
        )
        return JsonResponse({'status': 'ok', 'message': 'Factory reset command sent.'})
    return JsonResponse({'status': 'error'}, status=405)


@login_required
def ont_signal_data(request, pk):
    ont = get_object_or_404(ONT, pk=pk)
    history = SignalHistory.objects.filter(ont=ont).order_by('timestamp')[:48]
    return JsonResponse({
        'labels': [h.timestamp.strftime('%H:%M') for h in history],
        'rx_power': [h.rx_power for h in history],
        'tx_power': [h.tx_power for h in history],
        'olt_rx_power': [h.olt_rx_power for h in history],
    })


@login_required
def ont_traffic_data(request, pk):
    ont = get_object_or_404(ONT, pk=pk)
    history = TrafficHistory.objects.filter(ont=ont).order_by('timestamp')[:48]
    return JsonResponse({
        'labels': [h.timestamp.strftime('%H:%M') for h in history],
        'download': [h.download_mbps for h in history],
        'upload': [h.upload_mbps for h in history],
    })


@login_required
def profile_list(request):
    profiles = ONTProfile.objects.all()
    return render(request, 'onts/profiles.html', {'profiles': profiles})
