import psutil


def partition_usage():
    partitions = psutil.disk_partitions()
    reponse = list()
    for p in partitions:
        if 'rw' in p.opts and '/boot' not in p.mountpoint:
            usage = psutil.disk_usage(p.mountpoint)
            reponse.append({'mountpoint': p.mountpoint, 'free': usage.free, 'used': usage.used, 'total': usage.total})
    return reponse


def cpu_usage():
    load_avg = [round(l*100)/100 for l in list(psutil.getloadavg())]
    print("CPU ", load_avg)
    print("Disk IO", psutil.disk_io_counters())
    # print("CPU times ", psutil.cpu_times())
    # print("CPU times pct ", psutil.cpu_times_percent(interval=5))
    print("Temp ", psutil.sensors_temperatures())
    print("Fans ", psutil.sensors_fans())
    print("Battery ", psutil.sensors_battery())


if __name__ == '__main__':
    reponse = partition_usage()
    for p in reponse:
        print('Mount %s' % p)

    cpu_usage()

