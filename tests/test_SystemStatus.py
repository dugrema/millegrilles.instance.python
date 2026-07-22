import pytest
from unittest.mock import MagicMock, patch
from millegrilles_instance.SystemStatus import SystemStatus
import psutil
import time
import sys
import asyncio

@pytest.fixture
def system_status():
    return SystemStatus()

def test_partition_usage(system_status):
    # Mocking psutil.disk_partitions
    mock_p1 = MagicMock()
    mock_p1.mountpoint = "/mnt/data"
    mock_p1.opts = "rw,relatime"
    
    mock_p2 = MagicMock()
    mock_p2.mountpoint = "/boot"
    mock_p2.opts = "rw,relatime"

    mock_p3 = MagicMock()
    mock_p3.mountpoint = "/media/usb"
    mock_p3.opts = "ro,remount"

    with patch('psutil.disk_partitions', return_value=[mock_p1, mock_p2, mock_p3]):
        with patch('psutil.disk_usage') as mock_disk_usage:
            mock_usage = MagicMock()
            mock_usage.free = 1000
            mock_usage.used = 500
            mock_usage.total = 1500
            mock_disk_usage.return_value = mock_usage

            usage = system_status.partition_usage()

            assert len(usage) == 1
            assert usage[0]['mountpoint'] == "/mnt/data"
            assert usage[0]['free'] == 1000
            assert usage[0]['used'] == 500
            assert usage[0]['total'] == 1500

def test_read_system_status_all_metrics(system_status):
    # Mocking all psutil calls
    with patch('psutil.getloadavg', return_value=(1.0, 1.1, 1.2)), \
         patch('psutil.virtual_memory', return_value=MagicMock(total=100, available=60, percent=40, used=40, free=60)), \
         patch('psutil.swap_memory', return_value=MagicMock(total=50, used=10, free=40, percent=20)), \
         patch('psutil.cpu_count', return_value=4), \
         patch('psutil.cpu_percent', return_value=10.0), \
         patch('psutil.net_io_counters', return_value=MagicMock(bytes_sent=100, bytes_recv=200, packets_sent=10, packets_recv=20, errin=0, errout=0, dropin=0, dropout=0)), \
         patch('psutil.disk_io_counters', return_value=MagicMock(read_bytes=1000, write_bytes=2000, read_count=5, write_count=10, read_time=100, write_time=200)), \
         patch('psutil.boot_time', return_value=1000.0), \
         patch('time.time', return_value=2000.0), \
         patch('psutil.disk_partitions', return_value=[]), \
         patch('psutil.sensors_temperatures', return_value={}), \
         patch('psutil.sensors_fans', return_value={}), \
         patch('psutil.sensors_battery', return_value=None):

        system_status.read_system_status()
        state = system_status.current_state

        assert state['load_average'] == [1.0, 1.1, 1.2]
        assert state['memory']['total'] == 100
        assert state['cpu_count'] == 4
        assert state['cpu_usage_percent'] == 10.0
        assert state['uptime_seconds'] == 1000.0
        assert state['network']['bytes_sent'] == 100
        assert state['disk_io']['read_bytes'] == 1000

def test_read_system_status_missing_sensors(system_status):
    # Mocking psutil to raise AttributeError for sensors
    with patch('psutil.getloadavg', return_value=(0.5, 0.5, 0.5)), \
         patch('psutil.virtual_memory', return_value=MagicMock(total=10, available=5, percent=50, used=5, free=5)), \
         patch('psutil.swap_memory', return_value=MagicMock(total=10, used=0, free=10, percent=0)), \
         patch('psutil.cpu_count', return_value=1), \
         patch('psutil.cpu_percent', return_value=0.0), \
         patch('psutil.net_io_counters', return_value=MagicMock(bytes_sent=0, bytes_recv=0, packets_sent=0, packets_recv=0, errin=0, errout=0, dropin=0, dropout=0)), \
         patch('psutil.disk_io_counters', return_value=MagicMock(read_bytes=0, write_bytes=0, read_count=0, write_count=0, read_time=0, write_time=0)), \
         patch('psutil.boot_time', return_value=0.0), \
         patch('time.time', return_value=0.0), \
         patch('psutil.disk_partitions', return_value=[]), \
         patch('psutil.sensors_temperatures', side_effect=AttributeError), \
         patch('psutil.sensors_fans', side_effect=AttributeError), \
         patch('psutil.sensors_battery', side_effect=AttributeError):

        # Should not raise exception
        system_status.read_system_status()
        state = system_status.current_state
        assert 'system_temperature' not in state
        assert 'system_fans' not in state
        assert 'system_battery' not in state

def test_apc_info_success(system_status):
    with patch('apcaccess.status.get', return_value="UPTIME 10\nVOLTAGE 230.0\n"), \
         patch('apcaccess.status.parse', return_value={'UPTIME': 10, 'VOLTAGE': 230.0}):
        asyncio.run(system_status.apc_info())
        assert system_status._SystemStatus__apc_info == {'UPTIME': 10, 'VOLTAGE': 230.0}

def test_apc_info_failure(system_status):
    with patch('apcaccess.status.get', side_effect=Exception("Connection error")):
        asyncio.run(system_status.apc_info())
        assert system_status._SystemStatus__apc_info is False




