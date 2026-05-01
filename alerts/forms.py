from django import forms
from .models import AlertRule


class AlertRuleForm(forms.ModelForm):
    class Meta:
        model = AlertRule
        fields = [
            'name', 'type', 'threshold', 'operator', 'enabled',
            'notify_email', 'notify_sms', 'email_recipients', 'sms_recipients',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'operator': forms.Select(attrs={'class': 'form-select'}),
            'enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_sms': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_recipients': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                                      'placeholder': 'admin@isp.com, noc@isp.com'}),
            'sms_recipients': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                                    'placeholder': '+8801700000000, +8801800000000'}),
        }
