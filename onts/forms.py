from django import forms
from .models import ONT, ONTProfile
from olts.models import OLT, PONPort


class ONTProfileForm(forms.ModelForm):
    class Meta:
        model = ONTProfile
        fields = ['name', 'vendor', 'download_speed', 'upload_speed', 'protocol', 'vlan_id', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'vendor': forms.Select(attrs={'class': 'form-select'}),
            'download_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'upload_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'protocol': forms.Select(attrs={'class': 'form-select'}),
            'vlan_id': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ONTForm(forms.ModelForm):
    class Meta:
        model = ONT
        fields = [
            'olt', 'pon_port', 'ont_id', 'serial_number', 'name', 'description',
            'technology', 'mode', 'ip_address', 'mac_address',
            'vlan', 'profile', 'address', 'latitude', 'longitude',
        ]
        widgets = {
            'olt': forms.Select(attrs={'class': 'form-select'}),
            'pon_port': forms.Select(attrs={'class': 'form-select'}),
            'ont_id': forms.NumberInput(attrs={'class': 'form-control'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'technology': forms.Select(attrs={'class': 'form-select'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control'}),
            'mac_address': forms.TextInput(attrs={'class': 'form-control'}),
            'vlan': forms.NumberInput(attrs={'class': 'form-control'}),
            'profile': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
        }
