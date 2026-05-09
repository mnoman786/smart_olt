"""
Celery tasks for alert rule evaluation and notification dispatch.

Triggered automatically after each ONT / OLT poll cycle.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compare(value: float, operator: str, threshold: float) -> bool:
    """Evaluate a threshold comparison."""
    if threshold is None:
        return True  # threshold-less rules (e.g. ont_offline) always trigger on event
    if operator == 'lt':
        return value < threshold
    if operator == 'gt':
        return value > threshold
    if operator == 'eq':
        return value == threshold
    return False


def _send_email_notification(rule, subject: str, body: str):
    """Send email to all comma-separated recipients in rule.email_recipients."""
    from django.core.mail import send_mail
    from django.conf import settings
    from .models import AlertNotification

    recipients = [r.strip() for r in rule.email_recipients.split(',') if r.strip()]
    if not recipients:
        return

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        for recipient in recipients:
            AlertNotification.objects.create(
                rule=rule,
                channel='email',
                recipient=recipient,
                message=body,
                delivered=True,
            )
        logger.info('Alert email sent for rule "%s" to %s', rule.name, recipients)
    except Exception as exc:
        logger.error('Failed to send alert email for rule "%s": %s', rule.name, exc)
        for recipient in recipients:
            AlertNotification.objects.create(
                rule=rule,
                channel='email',
                recipient=recipient,
                message=body,
                delivered=False,
            )


# ── Celery tasks ──────────────────────────────────────────────────────────────

@shared_task(name='alerts.check_signal_alerts')
def check_signal_alerts(ont_id: int):
    """
    Evaluate signal-based alert rules for a single ONT after a poll update.
    Creates monitoring Events and sends notifications when thresholds are breached.
    """
    from onts.models import ONT
    from monitoring.models import Event
    from .models import AlertRule

    try:
        ont = ONT.objects.select_related('olt', 'pon_port').get(pk=ont_id)
    except ONT.DoesNotExist:
        return {'error': f'ONT {ont_id} not found'}

    triggered = 0
    for rule in AlertRule.objects.filter(enabled=True, type__in=['signal_low', 'signal_high']):
        if ont.status != 'online':
            continue
        if _compare(ont.rx_power, rule.operator, rule.threshold):
            msg = (
                f'[{rule.name}] ONT "{ont.name}" ({ont.serial_number}) '
                f'RX power {ont.rx_power} dBm '
                f'{"below" if rule.operator == "lt" else "above"} threshold '
                f'{rule.threshold} dBm on OLT {ont.olt.name}.'
            )
            Event.objects.create(
                type='signal_degraded',
                severity='warning',
                olt=ont.olt,
                ont=ont,
                message=msg,
            )
            if rule.notify_email and rule.email_recipients:
                _send_email_notification(
                    rule,
                    subject=f'[SmartOLT] {rule.name} — {ont.name}',
                    body=msg,
                )
            triggered += 1

    return {'ont': ont_id, 'rules_triggered': triggered}


@shared_task(name='alerts.check_ont_offline_alert')
def check_ont_offline_alert(ont_id: int):
    """
    Fire ONT-offline alert rules when an ONT transitions to offline.
    Call this from the polling code whenever an ONT status changes to offline.
    """
    from onts.models import ONT
    from monitoring.models import Event
    from .models import AlertRule

    try:
        ont = ONT.objects.select_related('olt').get(pk=ont_id)
    except ONT.DoesNotExist:
        return {'error': f'ONT {ont_id} not found'}

    if ont.status not in ('offline', 'los', 'power_failure', 'fiber_cut'):
        return {'skipped': 'ONT is not offline'}

    for rule in AlertRule.objects.filter(enabled=True, type='ont_offline'):
        msg = (
            f'[{rule.name}] ONT "{ont.name}" ({ont.serial_number}) '
            f'is {ont.get_status_display()} on OLT {ont.olt.name}.'
        )
        Event.objects.create(
            type='offline',
            severity='warning',
            olt=ont.olt,
            ont=ont,
            message=msg,
        )
        if rule.notify_email and rule.email_recipients:
            _send_email_notification(
                rule,
                subject=f'[SmartOLT] {rule.name} — {ont.name}',
                body=msg,
            )

    return {'ont': ont_id, 'processed': True}


@shared_task(name='alerts.check_olt_offline_alert')
def check_olt_offline_alert(olt_id: int):
    """
    Fire OLT-offline alert rules when an OLT transitions to offline.
    """
    from olts.models import OLT
    from monitoring.models import Event
    from .models import AlertRule

    try:
        olt = OLT.objects.get(pk=olt_id)
    except OLT.DoesNotExist:
        return {'error': f'OLT {olt_id} not found'}

    if olt.status != 'offline':
        return {'skipped': 'OLT is not offline'}

    for rule in AlertRule.objects.filter(enabled=True, type='olt_offline'):
        msg = (
            f'[{rule.name}] OLT "{olt.name}" ({olt.ip_address}) '
            f'is offline. All connected ONTs may be affected.'
        )
        Event.objects.create(
            type='olt_offline',
            severity='critical',
            olt=olt,
            message=msg,
        )
        if rule.notify_email and rule.email_recipients:
            _send_email_notification(
                rule,
                subject=f'[SmartOLT] {rule.name} — {olt.name}',
                body=msg,
            )

    return {'olt': olt_id, 'processed': True}


@shared_task(name='alerts.check_temperature_alerts')
def check_temperature_alerts(olt_id: int):
    """
    Evaluate temperature alert rules for a single OLT after a poll update.
    """
    from olts.models import OLT
    from monitoring.models import Event
    from .models import AlertRule

    try:
        olt = OLT.objects.get(pk=olt_id)
    except OLT.DoesNotExist:
        return {'error': f'OLT {olt_id} not found'}

    triggered = 0
    for rule in AlertRule.objects.filter(enabled=True, type='temperature'):
        if _compare(olt.temperature, rule.operator, rule.threshold):
            msg = (
                f'[{rule.name}] OLT "{olt.name}" temperature is '
                f'{olt.temperature}°C — '
                f'{"above" if rule.operator == "gt" else "below"} threshold '
                f'{rule.threshold}°C.'
            )
            Event.objects.create(
                type='signal_degraded',
                severity='warning',
                olt=olt,
                message=msg,
            )
            if rule.notify_email and rule.email_recipients:
                _send_email_notification(
                    rule,
                    subject=f'[SmartOLT] {rule.name} — {olt.name}',
                    body=msg,
                )
            triggered += 1

    return {'olt': olt_id, 'rules_triggered': triggered}
