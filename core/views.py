from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from olts.models import OLT
from onts.models import ONT
from monitoring.models import Event
from alerts.models import AlertRule


@login_required
def dashboard(request):
    total_olts = OLT.objects.count()
    online_olts = OLT.objects.filter(status='online').count()
    total_onts = ONT.objects.count()
    online_onts = ONT.objects.filter(status='online').count()
    offline_onts = ONT.objects.filter(status='offline').count()
    fault_onts = ONT.objects.filter(status__in=['los', 'power_failure', 'fiber_cut']).count()
    critical_events = Event.objects.filter(severity='critical', acknowledged=False).count()
    recent_events = Event.objects.select_related('olt', 'ont').order_by('-timestamp')[:10]

    olt_status = list(OLT.objects.values('status').annotate(count=Count('status')))
    ont_status_data = {
        'online': online_onts,
        'offline': offline_onts,
        'fault': fault_onts,
        'other': total_onts - online_onts - offline_onts - fault_onts,
    }

    poor_signal_onts = ONT.objects.filter(status='online', rx_power__lt=-27).select_related('olt')[:5]
    top_olts = OLT.objects.annotate(total=Count('onts')).order_by('-total')[:5]

    return render(request, 'core/dashboard.html', {
        'total_olts': total_olts,
        'online_olts': online_olts,
        'total_onts': total_onts,
        'online_onts': online_onts,
        'offline_onts': offline_onts,
        'fault_onts': fault_onts,
        'critical_events': critical_events,
        'recent_events': recent_events,
        'ont_status_data': ont_status_data,
        'poor_signal_onts': poor_signal_onts,
        'top_olts': top_olts,
    })


@login_required
def api_stats(request):
    return JsonResponse({
        'total_olts': OLT.objects.count(),
        'online_olts': OLT.objects.filter(status='online').count(),
        'total_onts': ONT.objects.count(),
        'online_onts': ONT.objects.filter(status='online').count(),
        'offline_onts': ONT.objects.filter(status='offline').count(),
        'fault_onts': ONT.objects.filter(status__in=['los', 'power_failure', 'fiber_cut']).count(),
        'critical_alerts': Event.objects.filter(severity='critical', acknowledged=False).count(),
    })
