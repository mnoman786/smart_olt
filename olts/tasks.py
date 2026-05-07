"""
Celery tasks for OLT polling.

Scale guide (1000+ OLTs):
  - poll_all_olts  → scheduled every 5 min by Celery Beat
  - poll_olt_stats → one task per OLT, runs on any available worker
  - poll_olt_onts  → one task per OLT, updates ONT statuses + signal history
  - send_ont_command → on-demand (reboot / factory_reset)

Worker startup:
  celery -A smartolt worker -l info --concurrency=20
Beat startup:
  celery -A smartolt beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30,
             name='olts.poll_olt_stats')
def poll_olt_stats(self, olt_id: int) -> dict:
    """Poll CPU / memory / temperature for one OLT and store an OLTMetrics row."""
    from .models import OLT
    from .ssh_service import poll_olt_stats_sync

    try:
        olt = OLT.objects.get(pk=olt_id)
    except OLT.DoesNotExist:
        return {'error': f'OLT {olt_id} not found'}

    try:
        result = poll_olt_stats_sync(olt)
        logger.info('Polled OLT %s: cpu=%.1f%% mem=%.1f%% temp=%.1f°C',
                    olt.name, result.get('cpu_usage', 0),
                    result.get('memory_usage', 0), result.get('temperature', 0))
        return result
    except Exception as exc:
        logger.error('poll_olt_stats OLT %s: %s', olt_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30,
             name='olts.poll_olt_onts')
def poll_olt_onts(self, olt_id: int) -> dict:
    """Update ONT statuses and signal readings for all ONTs on one OLT."""
    from .models import OLT
    from .ssh_service import poll_all_ont_signals_sync

    try:
        olt = OLT.objects.get(pk=olt_id)
    except OLT.DoesNotExist:
        return {'error': f'OLT {olt_id} not found'}

    try:
        count = poll_all_ont_signals_sync(olt)
        logger.info('Polled ONTs for OLT %s: %d updated', olt.name, count)
        return {'updated': count}
    except Exception as exc:
        logger.error('poll_olt_onts OLT %s: %s', olt_id, exc)
        raise self.retry(exc=exc)


@shared_task(name='olts.poll_all_olts')
def poll_all_olts() -> dict:
    """
    Fan-out polling to all active OLTs.
    Registered in Celery Beat to run every 5 minutes.
    """
    from .models import OLT

    olt_ids = list(OLT.objects.filter(is_active=True).values_list('id', flat=True))
    for olt_id in olt_ids:
        poll_olt_stats.delay(olt_id)
        poll_olt_onts.delay(olt_id)

    logger.info('Dispatched polling tasks for %d OLTs', len(olt_ids))
    return {'dispatched': len(olt_ids)}


@shared_task(bind=True, max_retries=0, name='olts.setup_new_olt')
def setup_new_olt(self, olt_id: int) -> dict:
    """
    Fired immediately after a new OLT is saved.
    1. Tests SSH connectivity → updates OLT.status
    2. If connected, syncs PON ports + ONTs from the device.
    Returns a summary dict stored as the task result.
    """
    from .models import OLT
    from .ssh_service import _test_ssh_raw, sync_olt_from_device_sync

    try:
        olt = OLT.objects.get(pk=olt_id)
    except OLT.DoesNotExist:
        return {'error': f'OLT {olt_id} not found', 'connected': False}

    conn = _test_ssh_raw(
        host=str(olt.ip_address),
        port=olt.ssh_port,
        username=olt.username,
        password=olt.password,
    )

    new_status = 'online' if conn['connected'] else 'offline'
    OLT.objects.filter(pk=olt_id).update(status=new_status)

    if not conn['connected']:
        return {'connected': False, 'error': conn['error'], 'ports_found': 0, 'onts_found': 0}

    sync = sync_olt_from_device_sync(olt)
    logger.info('setup_new_olt OLT %s: ports=%d onts=%d', olt.name,
                sync['ports_found'], sync['onts_found'])
    return {
        'connected': True,
        'ports_found': sync['ports_found'],
        'onts_found': sync['onts_found'],
        'error': sync.get('error', ''),
    }


@shared_task(bind=True, max_retries=1, default_retry_delay=10,
             name='olts.send_ont_command')
def send_ont_command(self, olt_id: int, ont_id: int, command: str) -> dict:
    """
    Execute a command on an ONT via SSH.
    command: 'reboot' | 'factory_reset'
    """
    from onts.models import ONT
    from monitoring.models import Event
    from .ssh_service import send_ont_command_sync

    try:
        ont = ONT.objects.select_related('olt', 'pon_port').get(pk=ont_id)
    except ONT.DoesNotExist:
        return {'success': False, 'message': f'ONT {ont_id} not found'}

    try:
        result = send_ont_command_sync(ont, command)
        severity = 'info' if command == 'reboot' else 'warning'
        event_type = command  # matches Event.TYPE_CHOICES
        Event.objects.create(
            type=event_type,
            severity=severity,
            olt=ont.olt,
            ont=ont,
            message=f'{command.replace("_", " ").title()} — {result["message"]}',
        )
        return result
    except Exception as exc:
        logger.error('send_ont_command ONT %s cmd=%s: %s', ont_id, command, exc)
        raise self.retry(exc=exc)
