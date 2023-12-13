import socket


def main():
    fqdn = socket.getfqdn()
    print("FQDN : %s" % fqdn)
    hostname = socket.gethostname()
    print("hostname : %s" % hostname)
    hostnames_ip = socket.gethostbyaddr(hostname)
    print("hostname by ip : %s" % str(hostnames_ip))

    hostnames_list = list()
    hostnames_list.append(hostnames_ip[0])
    hostnames_list.extend(hostnames_ip[1])

    hostnames_fqdn = list()
    for h in hostnames_list:
        try:
            h.index('.')
            hostnames_fqdn.append(h)
        except ValueError:
            pass

    print("Hostnames FQDN : %s" % hostnames_fqdn)


if __name__ == '__main__':
    main()
