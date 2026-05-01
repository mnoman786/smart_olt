from monitoring.models import Event


def global_context(request):
    if not request.user.is_authenticated:
        return {}
    try:
        critical_events_count = Event.objects.filter(severity='critical', acknowledged=False).count()
    except Exception:
        critical_events_count = 0
    return {'critical_events_count': critical_events_count}
