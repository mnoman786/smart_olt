from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Avg
from django.utils import timezone
from datetime import timedelta
from .models import SignalHistory, TrafficHistory, Event
from onts.models import ONT
from olts.models import OLT


@login_required
def signals_view(request):
    search = request.GET.get('q', '')
    quality = request.GET.get('quality', '')
    onts = ONT.objects.select_related('olt', 'pon_port').filter(status='online')
    if search:
        onts = onts.filter(Q(name__icontains=search) | Q(serial_number__icontains=search))
    if quality == 'poor':
        onts = onts.filter(rx_power__lt=-27)
    elif quality == 'fair':
        onts = onts.filter(rx_power__gte=-27, rx_power__lt=-23)
    elif quality == 'good':
        onts = onts.filter(rx_power__gte=-23)
    return render(request, 'monitoring/signals.html', {
        'onts': onts,
        'search': search,
        'quality_filter': quality,
    })


@login_required
def traffic_view(request):
    olt_id = request.GET.get('olt', '')
    onts = ONT.objects.select_related('olt').filter(status='online')
    olts = OLT.objects.all()
    if olt_id:
        onts = onts.filter(olt_id=olt_id)
    return render(request, 'monitoring/traffic.html', {
        'onts': onts,
        'olts': olts,
        'olt_filter': olt_id,
    })


@login_required
def events_view(request):
    severity = request.GET.get('severity', '')
    event_type = request.GET.get('type', '')
    olt_id = request.GET.get('olt', '')
    acknowledged = request.GET.get('ack', '')
    search = request.GET.get('q', '')

    events = Event.objects.select_related('olt', 'ont').order_by('-timestamp')
    if severity:
        events = events.filter(severity=severity)
    if event_type:
        events = events.filter(type=event_type)
    if olt_id:
        events = events.filter(olt_id=olt_id)
    if acknowledged == 'yes':
        events = events.filter(acknowledged=True)
    elif acknowledged == 'no':
        events = events.filter(acknowledged=False)
    if search:
        events = events.filter(message__icontains=search)

    events = events[:200]
    olts = OLT.objects.all()
    return render(request, 'monitoring/events.html', {
        'events': events,
        'olts': olts,
        'severity_filter': severity,
        'type_filter': event_type,
        'olt_filter': olt_id,
        'ack_filter': acknowledged,
        'search': search,
        'type_choices': Event.TYPE_CHOICES,
    })


@login_required
def acknowledge_event(request, pk):
    if request.method == 'POST':
        event = get_object_or_404(Event, pk=pk)
        event.acknowledged = True
        event.save(update_fields=['acknowledged'])
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=405)


@login_required
def signals_chart_data(request):
    onts = ONT.objects.filter(status='online').order_by('rx_power')[:20]
    return JsonResponse({
        'labels': [o.name for o in onts],
        'rx_power': [o.rx_power for o in onts],
        'tx_power': [o.tx_power for o in onts],
    })


@login_required
def traffic_chart_data(request):
    since = timezone.now() - timedelta(hours=24)
    from django.db.models import Sum
    data = (
        TrafficHistory.objects
        .filter(timestamp__gte=since)
        .extra(select={'hour': "strftime('%H', timestamp)"})
        .values('hour')
        .annotate(dl=Avg('download_mbps'), ul=Avg('upload_mbps'))
        .order_by('hour')
    )
    return JsonResponse({
        'labels': [f"{d['hour']}:00" for d in data],
        'download': [round(d['dl'], 2) for d in data],
        'upload': [round(d['ul'], 2) for d in data],
    })
