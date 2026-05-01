from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


# ── Shared constants ─────────────────────────────────────────────────────────

SIGNAL_EXCELLENT = -20
SIGNAL_GOOD = -23
SIGNAL_FAIR = -27

VENDOR_CHOICES = [('ZTE', 'ZTE'), ('HUAWEI', 'Huawei')]

STATUS_BADGE = {
    'online':        'bg-success',
    'offline':       'bg-danger',
    'warning':       'bg-warning text-dark',
    'unknown':       'bg-secondary',
    'los':           'bg-danger',
    'power_failure': 'bg-warning text-dark',
    'fiber_cut':     'bg-danger',
    'degraded':      'bg-warning text-dark',
    'provisioning':  'bg-info',
}

SEVERITY_BADGE = {
    'info':     'bg-info',
    'warning':  'bg-warning text-dark',
    'critical': 'bg-danger',
}

SEVERITY_ICON = {
    'info':     'fa-circle-info',
    'warning':  'fa-triangle-exclamation',
    'critical': 'fa-circle-xmark',
}


def format_uptime(seconds):
    if not seconds:
        return 'N/A'
    days  = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins  = (seconds % 3600) // 60
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


# ── Permission decorators ─────────────────────────────────────────────────────

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.profile.is_admin:
            messages.error(request, 'Access denied. Administrator privileges required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def operator_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.profile.is_operator:
            messages.error(request, 'Access denied. Operator privileges required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped
