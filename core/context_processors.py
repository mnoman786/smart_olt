from django.core.cache import cache
from monitoring.models import Event


def global_context(request):
    if not request.user.is_authenticated:
        return {}
    count = cache.get('critical_events_count')
    if count is None:
        try:
            count = Event.objects.filter(severity='critical', acknowledged=False).count()
        except Exception:
            count = 0
        cache.set('critical_events_count', count, 60)
    return {'critical_events_count': count}
