import random
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Clear all OLT/PON/ONT data and create demo dummy data'

    def handle(self, *args, **options):
        self.stdout.write('Clearing existing data...')
        self._clear()
        self.stdout.write('Creating demo data...')
        self._create()
        self.stdout.write(self.style.SUCCESS('Demo data created successfully.'))

    @transaction.atomic
    def _clear(self):
        from monitoring.models import SignalHistory, TrafficHistory, OLTMetrics, Event
        from alerts.models import AlertRule
        from onts.models import ONT, ONTProfile
        from olts.models import OLT, PONPort

        Event.objects.all().delete()
        SignalHistory.objects.all().delete()
        TrafficHistory.objects.all().delete()
        OLTMetrics.objects.all().delete()
        AlertRule.objects.all().delete()
        ONT.objects.all().delete()
        PONPort.objects.all().delete()
        OLT.objects.all().delete()
        ONTProfile.objects.all().delete()

    @transaction.atomic
    def _create(self):
        from olts.models import OLT, PONPort
        from onts.models import ONT, ONTProfile

        profile_home = ONTProfile.objects.create(
            name='Home-100M', vendor='ZTE',
            download_speed=100, upload_speed=50, protocol='dhcp', vlan_id=100,
        )
        profile_biz = ONTProfile.objects.create(
            name='Business-1G', vendor='ZTE',
            download_speed=1000, upload_speed=500, protocol='pppoe', vlan_id=200,
        )

        olt = OLT.objects.create(
            name='ZTE-C600-Main',
            vendor='ZTE',
            model='ZTE C600',
            ip_address='192.168.1.1',
            telnet_port=23,
            ssh_port=22,
            username='admin',
            password='admin123',
            location='Data Center - Rack A3',
            status='online',
            snmp_community='public',
            firmware_version='V1.2.3P4T6',
            uptime=86400 * 12 + 3600 * 5,
            cpu_usage=34.5,
            memory_usage=61.2,
            temperature=42.0,
        )

        port_specs = [
            (1, 1, 8, 5),
            (1, 2, 14, 11),
            (1, 3, 6, 4),
            (1, 4, 20, 17),
            (2, 1, 3, 2),
            (2, 2, 10, 8),
            (2, 3, 0, 0),
            (2, 4, 5, 3),
        ]

        statuses_offline = ['offline', 'los', 'power_failure', 'fiber_cut']
        rx_vals = [-16.5, -18.2, -19.8, -21.3, -22.7, -24.1, -25.6, -27.9, -30.2]

        serial_counter = 1000

        for board, port_num, total_onts, online_onts in port_specs:
            pon = PONPort.objects.create(
                olt=olt,
                board=board,
                port=port_num,
                technology='GPON',
                status='up' if total_onts > 0 else 'down',
                max_onts=128,
            )

            offline_onts = total_onts - online_onts
            ont_id = 1

            for _ in range(online_onts):
                serial_counter += 1
                rx = random.choice(rx_vals[:6])
                ONT.objects.create(
                    olt=olt,
                    pon_port=pon,
                    ont_id=ont_id,
                    serial_number=f'ZTEG{serial_counter:08d}',
                    name=f'ONT-B{board}P{port_num}-{ont_id:03d}',
                    status='online',
                    technology='GPON',
                    mode='routing',
                    ip_address=f'10.{board}.{port_num}.{ont_id}',
                    rx_power=rx,
                    tx_power=2.5,
                    olt_rx_power=rx + 0.3,
                    distance=random.uniform(0.5, 15.0),
                    vlan=100,
                    uptime=random.randint(3600, 86400 * 30),
                    profile=random.choice([profile_home, profile_biz]),
                )
                ont_id += 1

            for _ in range(offline_onts):
                serial_counter += 1
                ONT.objects.create(
                    olt=olt,
                    pon_port=pon,
                    ont_id=ont_id,
                    serial_number=f'ZTEG{serial_counter:08d}',
                    name=f'ONT-B{board}P{port_num}-{ont_id:03d}',
                    status=random.choice(statuses_offline),
                    technology='GPON',
                    mode='routing',
                    ip_address=None,
                    rx_power=-35.0,
                    tx_power=0.0,
                    olt_rx_power=-35.0,
                    distance=random.uniform(0.5, 15.0),
                    vlan=100,
                    uptime=0,
                )
                ont_id += 1
