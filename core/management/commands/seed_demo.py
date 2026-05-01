import random
import string
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed the database with realistic demo data for SmartOLT Cloud'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('Clearing existing data...'))
        self._clear_data()

        self.stdout.write('Creating users...')
        self._create_users()

        self.stdout.write('Creating OLTs...')
        self._create_olts()

        self.stdout.write('Creating PON ports...')
        self._create_pon_ports()

        self.stdout.write('Creating ONT profiles...')
        self._create_ont_profiles()

        self.stdout.write('Creating ONTs...')
        self._create_onts()

        self.stdout.write('Creating history data...')
        self._create_history()

        self.stdout.write('Creating events...')
        self._create_events()

        self.stdout.write('Creating alert rules...')
        self._create_alert_rules()

        self.stdout.write(self.style.SUCCESS('\nDemo data created successfully!'))
        self.stdout.write(self.style.SUCCESS('Login: admin / admin123'))

    def _clear_data(self):
        from monitoring.models import SignalHistory, TrafficHistory, OLTMetrics, Event
        from alerts.models import AlertRule, AlertNotification
        from onts.models import ONT, ONTProfile
        from olts.models import OLT, PONPort
        SignalHistory.objects.all().delete()
        TrafficHistory.objects.all().delete()
        OLTMetrics.objects.all().delete()
        Event.objects.all().delete()
        AlertNotification.objects.all().delete()
        AlertRule.objects.all().delete()
        ONT.objects.all().delete()
        ONTProfile.objects.all().delete()
        PONPort.objects.all().delete()
        OLT.objects.all().delete()
        User.objects.filter(username__in=['admin', 'operator1', 'operator2', 'viewer1']).delete()

    def _create_users(self):
        from accounts.models import UserProfile
        users = [
            ('admin', 'admin@smartolt.com', 'admin123', 'Admin', 'User', 'admin'),
            ('operator1', 'noc1@smartolt.com', 'operator123', 'John', 'Smith', 'operator'),
            ('operator2', 'noc2@smartolt.com', 'operator123', 'Jane', 'Doe', 'operator'),
            ('viewer1', 'viewer@smartolt.com', 'viewer123', 'Bob', 'Wilson', 'viewer'),
        ]
        for username, email, password, first, last, role in users:
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=first, last_name=last,
            )
            if role == 'admin':
                user.is_staff = True
                user.is_superuser = True
                user.save()
            profile = user.profile
            profile.role = role
            profile.organization = 'SmartOLT ISP'
            profile.phone = f'+880170{random.randint(1000000, 9999999)}'
            profile.save()

    def _create_olts(self):
        from olts.models import OLT
        olts_data = [
            {
                'name': 'Core-OLT-01', 'vendor': 'ZTE', 'model': 'C300',
                'ip_address': '192.168.1.100', 'location': 'Dhaka Main DC',
                'latitude': 23.8103, 'longitude': 90.4125,
                'status': 'online', 'firmware_version': 'V2.0.1P2T8',
                'cpu_usage': 32.5, 'memory_usage': 58.2, 'temperature': 42.0,
                'uptime': 1728000, 'description': 'Primary core OLT for Dhaka region',
            },
            {
                'name': 'Core-OLT-02', 'vendor': 'ZTE', 'model': 'C320',
                'ip_address': '192.168.1.101', 'location': 'Dhaka North POP',
                'latitude': 23.8223, 'longitude': 90.3654,
                'status': 'online', 'firmware_version': 'V2.0.1P2T8',
                'cpu_usage': 28.1, 'memory_usage': 62.4, 'temperature': 39.5,
                'uptime': 864000, 'description': 'North Dhaka distribution OLT',
            },
            {
                'name': 'Core-OLT-03', 'vendor': 'ZTE', 'model': 'C600',
                'ip_address': '192.168.1.102', 'location': 'Chittagong HQ',
                'latitude': 22.3569, 'longitude': 91.7832,
                'status': 'warning', 'firmware_version': 'V2.0.1P1T5',
                'cpu_usage': 78.3, 'memory_usage': 85.1, 'temperature': 57.2,
                'uptime': 432000, 'description': 'Chittagong region OLT - high load',
            },
            {
                'name': 'Core-OLT-04', 'vendor': 'HUAWEI', 'model': 'MA5600T',
                'ip_address': '192.168.1.103', 'location': 'Sylhet Central',
                'latitude': 24.8949, 'longitude': 91.8687,
                'status': 'online', 'firmware_version': 'V800R013C00',
                'cpu_usage': 21.4, 'memory_usage': 44.7, 'temperature': 38.0,
                'uptime': 2592000, 'description': 'Sylhet region primary OLT',
            },
            {
                'name': 'Core-OLT-05', 'vendor': 'HUAWEI', 'model': 'MA5800-X7',
                'ip_address': '192.168.1.104', 'location': 'Rajshahi POP',
                'latitude': 24.3745, 'longitude': 88.6042,
                'status': 'offline', 'firmware_version': 'V900R001C00',
                'cpu_usage': 0, 'memory_usage': 0, 'temperature': 0,
                'uptime': 0, 'description': 'Rajshahi region OLT - offline for maintenance',
            },
        ]
        self.olts = []
        for data in olts_data:
            olt = OLT.objects.create(**data)
            self.olts.append(olt)

    def _create_pon_ports(self):
        from olts.models import PONPort
        self.pon_ports = []
        port_configs = [
            (self.olts[0], [(1, i) for i in range(1, 5)]),  # OLT-01: board 1, ports 1-4
            (self.olts[1], [(1, i) for i in range(1, 4)]),  # OLT-02: board 1, ports 1-3
            (self.olts[2], [(1, i) for i in range(1, 4)]),  # OLT-03: board 1, ports 1-3
            (self.olts[3], [(0, i) for i in range(1, 4)]),  # OLT-04: board 0, ports 1-3
            (self.olts[4], [(0, i) for i in range(1, 3)]),  # OLT-05: board 0, ports 1-2
        ]
        for olt, ports in port_configs:
            for board, port in ports:
                tech = 'GPON' if olt.vendor == 'ZTE' else 'GPON'
                status = 'up' if olt.status != 'offline' else 'down'
                pp = PONPort.objects.create(
                    olt=olt, board=board, port=port,
                    technology=tech, status=status, max_onts=128,
                )
                self.pon_ports.append(pp)

    def _create_ont_profiles(self):
        from onts.models import ONTProfile
        profiles_data = [
            ('Basic 10/5', 'ALL', 10, 5, 'pppoe', 100),
            ('Standard 50/25', 'ALL', 50, 25, 'pppoe', 200),
            ('Premium 100/50', 'ALL', 100, 50, 'pppoe', 300),
            ('Business 200/100', 'ALL', 200, 100, 'static', 400),
            ('Enterprise 500/500', 'ALL', 500, 500, 'static', 500),
            ('IPTV Bridge', 'ALL', 100, 10, 'bridge', 600),
            ('ZTE Home', 'ZTE', 100, 50, 'dhcp', 700),
            ('Huawei Office', 'HUAWEI', 200, 100, 'static', 800),
        ]
        self.profiles = []
        for name, vendor, dl, ul, proto, vlan in profiles_data:
            p = ONTProfile.objects.create(
                name=name, vendor=vendor, download_speed=dl, upload_speed=ul,
                protocol=proto, vlan_id=vlan,
            )
            self.profiles.append(p)

    def _generate_serial(self, vendor):
        chars = string.ascii_uppercase + string.digits
        suffix = ''.join(random.choices(chars, k=8))
        return f"ZTEG{suffix}" if vendor == 'ZTE' else f"HWTC{suffix}"

    def _create_onts(self):
        from onts.models import ONT
        customer_names = [
            'Ahmed Hassan', 'Rahim Uddin', 'Karim Khan', 'Nasrin Begum', 'Fatima Ali',
            'Mohammad Islam', 'Ayesha Siddiqua', 'Jabbar Sheikh', 'Salam Hossain', 'Reza Mia',
            'Sumaiya Khatun', 'Rafiq Ahmed', 'Nargis Parvin', 'Babul Hasan', 'Mina Akter',
            'Liton Sarkar', 'Rony Talukder', 'Shirin Akter', 'Kawsar Ahmad', 'Dilruba Khanam',
        ]
        addresses = [
            'House 12, Road 5, Dhanmondi', 'Flat 3B, Mirpur 10', 'Plot 45, Uttara Sector 7',
            'Shop 2, Motijheel Commercial', 'House 8, Gulshan Avenue', 'Road 27, Banani',
            'House 55, Mohakhali', 'Block C, Bashundhara RA', 'Flat 7A, Shyamoli',
            'House 3, Rayer Bazar', 'East Nasirabad, Chittagong', 'Agrabad Commercial Area',
            'Panchlaish Residential', 'Halishahar Housing', 'Zindabazar, Sylhet',
            'Ambarkhana Point', 'Subidbazar, Sylhet', 'Rajpara, Rajshahi',
            'Boalia, Rajshahi', 'Shaheb Bazar, Rajshahi',
        ]

        statuses_weighted = (
            ['online'] * 60 + ['offline'] * 12 + ['los'] * 4 +
            ['power_failure'] * 2 + ['fiber_cut'] * 2
        )

        self.onts = []
        ont_counter = {}

        active_ports = [pp for pp in self.pon_ports if pp.olt.status != 'offline']
        all_ports = self.pon_ports

        count = 0
        for i in range(80):
            if count < 70:
                port = random.choice(active_ports)
            else:
                port = random.choice(all_ports)

            olt = port.olt
            port_key = port.id
            if port_key not in ont_counter:
                ont_counter[port_key] = 1
            else:
                ont_counter[port_key] += 1

            status = random.choice(statuses_weighted)
            if olt.status == 'offline':
                status = 'offline'

            is_online = status == 'online'
            rx = round(random.uniform(-28, -14), 2) if is_online else 0
            tx = round(random.uniform(2, 5), 2) if is_online else 0
            olt_rx = round(rx + random.uniform(-1, 1), 2) if is_online else 0
            distance = round(random.uniform(0.3, 15.0), 2) if is_online else 0
            uptime = random.randint(3600, 2592000) if is_online else 0

            name = customer_names[i % len(customer_names)]
            if i >= len(customer_names):
                name = f"{name} {i // len(customer_names) + 1}"

            ont = ONT.objects.create(
                olt=olt,
                pon_port=port,
                ont_id=ont_counter[port_key],
                serial_number=self._generate_serial(olt.vendor),
                name=name,
                status=status,
                technology='GPON',
                mode=random.choice(['routing', 'bridging']),
                ip_address=f'10.{random.randint(10,50)}.{random.randint(1,254)}.{random.randint(2,254)}' if is_online else None,
                mac_address=':'.join([f'{random.randint(0,255):02x}' for _ in range(6)]) if is_online else '',
                rx_power=rx,
                tx_power=tx,
                olt_rx_power=olt_rx,
                distance=distance,
                uptime=uptime,
                last_online=timezone.now() - timedelta(seconds=random.randint(0, 86400)) if not is_online else timezone.now(),
                profile=random.choice(self.profiles),
                vlan=random.choice([100, 200, 300, 400, 500]),
                address=addresses[i % len(addresses)],
                latitude=round(random.uniform(22.0, 25.0), 6),
                longitude=round(random.uniform(88.0, 92.0), 6),
            )
            self.onts.append(ont)
            count += 1

    def _create_history(self):
        from monitoring.models import SignalHistory, TrafficHistory, OLTMetrics
        now = timezone.now()
        bulk_signal = []
        bulk_traffic = []
        bulk_metrics = []

        online_onts = [o for o in self.onts if o.status == 'online']

        for ont in online_onts[:30]:
            base_rx = ont.rx_power
            base_tx = ont.tx_power
            base_olt_rx = ont.olt_rx_power
            for i in range(48):
                ts = now - timedelta(minutes=30 * (47 - i))
                rx = round(base_rx + random.uniform(-1.5, 1.5), 2)
                tx = round(base_tx + random.uniform(-0.5, 0.5), 2)
                olt_rx = round(base_olt_rx + random.uniform(-1.0, 1.0), 2)
                bulk_signal.append(SignalHistory(ont=ont, timestamp=ts, rx_power=rx, tx_power=tx, olt_rx_power=olt_rx))

                profile = ont.profile
                max_dl = profile.download_speed if profile else 100
                max_ul = profile.upload_speed if profile else 50
                peak_factor = 1.5 if 9 <= ts.hour <= 22 else 0.4
                dl = round(random.uniform(0, max_dl * peak_factor * 0.8), 2)
                ul = round(random.uniform(0, max_ul * peak_factor * 0.8), 2)
                bulk_traffic.append(TrafficHistory(ont=ont, timestamp=ts, download_mbps=dl, upload_mbps=ul))

        SignalHistory.objects.bulk_create(bulk_signal)
        TrafficHistory.objects.bulk_create(bulk_traffic)

        for olt in self.olts:
            if olt.status == 'offline':
                continue
            for i in range(48):
                ts = now - timedelta(minutes=30 * (47 - i))
                bulk_metrics.append(OLTMetrics(
                    olt=olt, timestamp=ts,
                    cpu_usage=round(olt.cpu_usage + random.uniform(-15, 15), 1),
                    memory_usage=round(olt.memory_usage + random.uniform(-10, 10), 1),
                    temperature=round(olt.temperature + random.uniform(-3, 3), 1),
                ))
        OLTMetrics.objects.bulk_create(bulk_metrics)

    def _create_events(self):
        from monitoring.models import Event
        now = timezone.now()
        bulk_events = []
        event_templates = [
            ('online', 'info', '{ont} came online on {port}.'),
            ('offline', 'warning', '{ont} went offline. Last seen: {ts}.'),
            ('los', 'critical', 'Loss of signal detected on {ont} ({serial}).'),
            ('power_failure', 'critical', 'Power failure detected on {ont}. Check UPS.'),
            ('fiber_cut', 'critical', 'Fiber cut suspected on {ont}. RX power: {rx} dBm.'),
            ('signal_degraded', 'warning', 'Signal degraded on {ont}: RX={rx} dBm (threshold: -27 dBm).'),
            ('olt_online', 'info', '{olt} OLT came online.'),
            ('olt_offline', 'critical', '{olt} OLT went offline — all ONTs affected.'),
            ('provisioned', 'info', 'New ONT {ont} ({serial}) provisioned successfully.'),
            ('rebooted', 'info', 'ONT {ont} rebooted remotely.'),
        ]
        for i in range(150):
            ts = now - timedelta(minutes=random.randint(1, 10080))
            tpl = random.choice(event_templates)
            etype, severity, msg_tpl = tpl
            ont = random.choice(self.onts)
            olt = ont.olt
            port = str(ont.pon_port) if ont.pon_port else 'N/A'
            msg = (msg_tpl
                   .replace('{ont}', ont.name)
                   .replace('{serial}', ont.serial_number)
                   .replace('{port}', port)
                   .replace('{olt}', olt.name)
                   .replace('{ts}', (ts - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M'))
                   .replace('{rx}', str(round(random.uniform(-32, -14), 1))))
            bulk_events.append(Event(
                type=etype, severity=severity, olt=olt, ont=ont if 'olt_' not in etype else None,
                message=msg, acknowledged=random.random() > 0.4,
            ))

        for evt in bulk_events:
            evt.timestamp = now - timedelta(minutes=random.randint(1, 10080))
        Event.objects.bulk_create(bulk_events)
        Event.objects.all().update()

    def _create_alert_rules(self):
        from alerts.models import AlertRule
        rules = [
            ('Low RX Signal Alert', 'signal_low', -27.0, 'lt', True, True, False,
             'noc@smartolt.com', ''),
            ('ONT Offline Alert', 'ont_offline', None, 'lt', True, True, True,
             'noc@smartolt.com,admin@smartolt.com', '+8801711000000'),
            ('OLT Offline Alert', 'olt_offline', None, 'lt', True, True, True,
             'admin@smartolt.com', '+8801711000000,+8801811000000'),
            ('High Temperature Warning', 'temperature', 55.0, 'gt', True, True, False,
             'noc@smartolt.com', ''),
            ('High Traffic Alert', 'high_traffic', 900.0, 'gt', False, True, False,
             'noc@smartolt.com', ''),
        ]
        for name, rtype, threshold, op, enabled, email, sms, email_rec, sms_rec in rules:
            AlertRule.objects.create(
                name=name, type=rtype, threshold=threshold, operator=op,
                enabled=enabled, notify_email=email, notify_sms=sms,
                email_recipients=email_rec, sms_recipients=sms_rec,
            )
