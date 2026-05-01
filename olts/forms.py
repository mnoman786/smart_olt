from django import forms
from .models import OLT, PONPort


class OLTForm(forms.ModelForm):
    class Meta:
        model = OLT
        fields = [
            'name', 'vendor', 'model', 'ip_address', 'telnet_port', 'ssh_port',
            'username', 'password', 'location', 'latitude', 'longitude',
            'description', 'snmp_community', 'firmware_version', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'vendor': forms.Select(attrs={'class': 'form-select'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control'}),
            'telnet_port': forms.NumberInput(attrs={'class': 'form-control'}),
            'ssh_port': forms.NumberInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'password': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'snmp_community': forms.TextInput(attrs={'class': 'form-control'}),
            'firmware_version': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PONPortForm(forms.ModelForm):
    class Meta:
        model = PONPort
        fields = ['board', 'port', 'technology', 'status', 'max_onts', 'description']
        widgets = {
            'board': forms.NumberInput(attrs={'class': 'form-control'}),
            'port': forms.NumberInput(attrs={'class': 'form-control'}),
            'technology': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'max_onts': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }
