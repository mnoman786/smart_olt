from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from .models import ONT, ONTProfile
from .forms import ONTForm, ONTProfileForm
from monitoring.models import SignalHistory, TrafficHistory, Event
from core.utils import operator_required, admin_required


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
    return render(request, 'onts/list.html', {
        'onts': onts,
        'search': search,
        'status_filter': status,
        'olt_filter': olt_id,
        'tech_filter': technology,
        'olts': OLT.objects.all(),
        'status_choices': ONT.STATUS_CHOICES,
    })


@login_required
def ont_detail(request, pk):
    ont = get_object_or_404(ONT.objects.select_related('olt', 'pon_port', 'profile'), pk=pk)
    recent_events = Event.objects.filter(ont=ont).order_by('-timestamp')[:20]
    return render(request, 'onts/detail.html', {'ont': ont, 'recent_events': recent_events})


@login_required
@operator_required
def ont_create(request):
    if request.method == 'POST':
        form = ONTForm(request.POST)
        if form.is_valid():
            ont = form.save()
            # Remove from discovered list now that it's registered
            from olts.models import DiscoveredONT
            DiscoveredONT.objects.filter(serial_number=ont.serial_number).delete()
            messages.success(request, f'ONT "{ont.name}" registered successfully.')
            return redirect('ont_detail', pk=ont.pk)
    else:
        # Pre-fill from query params (coming from "Register This ONT" button)
        initial = {}
        if request.GET.get('serial'):
            initial['serial_number'] = request.GET['serial']
        if request.GET.get('olt'):
            initial['olt'] = request.GET['olt']
        if request.GET.get('pon_port'):
            initial['pon_port'] = request.GET['pon_port']
        form = ONTForm(initial=initial)

    return render(request, 'onts/form.html', {
        'form': form,
        'action': 'Add ONT',
        'prefill_serial': request.GET.get('serial', ''),
    })


@login_required
@operator_required
def ont_edit(request, pk):
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
@admin_required
def ont_delete(request, pk):
    ont = get_object_or_404(ONT, pk=pk)
    if request.method == 'POST':
        name = ont.name
        ont.delete()
        messages.success(request, f'ONT "{name}" deleted.')
        return redirect('ont_list')
    return render(request, 'onts/confirm_delete.html', {'ont': ont})


@login_required
@operator_required
def ont_reboot(request, pk):
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=405)
    ont = get_object_or_404(ONT, pk=pk)
    try:
        from olts.tasks import send_ont_command
        task = send_ont_command.delay(ont.olt_id, ont.pk, 'reboot')
        return JsonResponse({'status': 'queued', 'task_id': task.id,
                             'message': 'Reboot command queued.'})
    except Exception:
        from olts.ssh_service import send_ont_command_sync
        result = send_ont_command_sync(ont, 'reboot')
        Event.objects.create(
            type='rebooted', severity='info', olt=ont.olt, ont=ont,
            message=f'ONT {ont.name} rebooted by {request.user.username}. {result.get("message", "")}'
        )
        return JsonResponse({'status': 'ok', 'message': result.get('message', 'Reboot command sent.')})


@login_required
@operator_required
def ont_factory_reset(request, pk):
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=405)
    ont = get_object_or_404(ONT, pk=pk)
    try:
        from olts.tasks import send_ont_command
        task = send_ont_command.delay(ont.olt_id, ont.pk, 'factory_reset')
        return JsonResponse({'status': 'queued', 'task_id': task.id,
                             'message': 'Factory reset command queued.'})
    except Exception:
        from olts.ssh_service import send_ont_command_sync
        result = send_ont_command_sync(ont, 'factory_reset')
        Event.objects.create(
            type='factory_reset', severity='warning', olt=ont.olt, ont=ont,
            message=f'ONT {ont.name} factory reset by {request.user.username}. {result.get("message", "")}'
        )
        return JsonResponse({'status': 'ok', 'message': result.get('message', 'Factory reset command sent.')})


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
    profiles = ONTProfile.objects.annotate(ont_count=Count('ont'))
    return render(request, 'onts/profiles.html', {'profiles': profiles})


@login_required
@operator_required
def profile_create(request):
    if request.method == 'POST':
        form = ONTProfileForm(request.POST)
        if form.is_valid():
            profile = form.save()
            messages.success(request, f'Profile "{profile.name}" created.')
            return redirect('ont_profiles')
    else:
        form = ONTProfileForm()
    return render(request, 'onts/profile_form.html', {'form': form, 'action': 'Add Profile'})


@login_required
@operator_required
def profile_edit(request, pk):
    profile = get_object_or_404(ONTProfile, pk=pk)
    if request.method == 'POST':
        form = ONTProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, f'Profile "{profile.name}" updated.')
            return redirect('ont_profiles')
    else:
        form = ONTProfileForm(instance=profile)
    return render(request, 'onts/profile_form.html', {'form': form, 'profile': profile, 'action': 'Edit Profile'})


@login_required
@admin_required
def profile_delete(request, pk):
    profile = get_object_or_404(ONTProfile, pk=pk)
    if request.method == 'POST':
        name = profile.name
        profile.delete()
        messages.success(request, f'Profile "{name}" deleted.')
        return redirect('ont_profiles')
    return render(request, 'onts/profile_confirm_delete.html', {'profile': profile})
