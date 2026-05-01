from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import AlertRule, AlertNotification
from .forms import AlertRuleForm


@login_required
def rules_list(request):
    rules = AlertRule.objects.all()
    return render(request, 'alerts/rules.html', {'rules': rules})


@login_required
def rule_create(request):
    if not request.user.profile.is_operator:
        messages.error(request, 'Access denied.')
        return redirect('rules_list')
    if request.method == 'POST':
        form = AlertRuleForm(request.POST)
        if form.is_valid():
            rule = form.save()
            messages.success(request, f'Alert rule "{rule.name}" created.')
            return redirect('rules_list')
    else:
        form = AlertRuleForm()
    return render(request, 'alerts/rule_form.html', {'form': form, 'action': 'Create Rule'})


@login_required
def rule_edit(request, pk):
    if not request.user.profile.is_operator:
        messages.error(request, 'Access denied.')
        return redirect('rules_list')
    rule = get_object_or_404(AlertRule, pk=pk)
    if request.method == 'POST':
        form = AlertRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, f'Alert rule "{rule.name}" updated.')
            return redirect('rules_list')
    else:
        form = AlertRuleForm(instance=rule)
    return render(request, 'alerts/rule_form.html', {'form': form, 'rule': rule, 'action': 'Edit Rule'})


@login_required
def rule_delete(request, pk):
    if not request.user.profile.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('rules_list')
    rule = get_object_or_404(AlertRule, pk=pk)
    if request.method == 'POST':
        name = rule.name
        rule.delete()
        messages.success(request, f'Alert rule "{name}" deleted.')
        return redirect('rules_list')
    return render(request, 'alerts/rule_confirm_delete.html', {'rule': rule})


@login_required
def notification_history(request):
    notifications = AlertNotification.objects.select_related('rule').order_by('-sent_at')[:100]
    return render(request, 'alerts/history.html', {'notifications': notifications})
