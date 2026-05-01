from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta, datetime
import csv
from onts.models import ONT
from olts.models import OLT
from monitoring.models import Event, SignalHistory, TrafficHistory


@login_required
def reports_index(request):
    report_type = request.GET.get('type', 'ont_status')
    olt_id = request.GET.get('olt', '')
    date_from = request.GET.get('from', (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
    date_to = request.GET.get('to', timezone.now().strftime('%Y-%m-%d'))

    try:
        dt_from = datetime.strptime(date_from, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, tzinfo=timezone.utc)
    except ValueError:
        dt_from = timezone.now() - timedelta(days=7)
        dt_to = timezone.now()

    olts = OLT.objects.all()
    context = {
        'report_type': report_type,
        'olt_id': olt_id,
        'date_from': date_from,
        'date_to': date_to,
        'olts': olts,
    }

    if report_type == 'ont_status':
        onts = ONT.objects.select_related('olt', 'pon_port')
        if olt_id:
            onts = onts.filter(olt_id=olt_id)
        context['onts'] = onts
        context['online_count'] = onts.filter(status='online').count()
        context['offline_count'] = onts.filter(status='offline').count()
        context['fault_count'] = onts.filter(status__in=['los', 'power_failure', 'fiber_cut']).count()

    elif report_type == 'signal':
        onts_qs = ONT.objects.select_related('olt').filter(status='online')
        if olt_id:
            onts_qs = onts_qs.filter(olt_id=olt_id)
        context['onts'] = onts_qs

    elif report_type == 'events':
        events = Event.objects.select_related('olt', 'ont').filter(
            timestamp__gte=dt_from, timestamp__lte=dt_to
        ).order_by('-timestamp')
        if olt_id:
            events = events.filter(olt_id=olt_id)
        context['events'] = events[:500]
        context['critical_count'] = events.filter(severity='critical').count()
        context['warning_count'] = events.filter(severity='warning').count()
        context['info_count'] = events.filter(severity='info').count()

    return render(request, 'reports/index.html', context)


@login_required
def export_csv(request):
    report_type = request.GET.get('type', 'ont_status')
    olt_id = request.GET.get('olt', '')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="smartolt_{report_type}.csv"'
    writer = csv.writer(response)

    if report_type == 'ont_status':
        writer.writerow(['Name', 'Serial', 'OLT', 'Port', 'Status', 'RX Power', 'TX Power', 'Distance', 'IP', 'Uptime'])
        onts = ONT.objects.select_related('olt', 'pon_port')
        if olt_id:
            onts = onts.filter(olt_id=olt_id)
        for o in onts:
            port = str(o.pon_port) if o.pon_port else ''
            writer.writerow([o.name, o.serial_number, o.olt.name, port, o.get_status_display(),
                             o.rx_power, o.tx_power, o.distance, o.ip_address or '', o.uptime_formatted])

    elif report_type == 'events':
        writer.writerow(['Timestamp', 'Type', 'Severity', 'OLT', 'ONT', 'Message'])
        events = Event.objects.select_related('olt', 'ont').order_by('-timestamp')[:1000]
        if olt_id:
            events = events.filter(olt_id=olt_id)
        for e in events:
            writer.writerow([e.timestamp.strftime('%Y-%m-%d %H:%M:%S'), e.get_type_display(),
                             e.severity, e.olt.name if e.olt else '', str(e.ont) if e.ont else '', e.message])

    return response
