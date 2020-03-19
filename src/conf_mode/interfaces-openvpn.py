#!/usr/bin/env python3
#
# Copyright (C) 2019 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import re

from jinja2 import Template
from copy import deepcopy
from sys import exit
from stat import S_IRUSR,S_IRWXU,S_IRGRP,S_IXGRP,S_IROTH,S_IXOTH
from grp import getgrnam
from ipaddress import ip_address,ip_network,IPv4Interface
from netifaces import interfaces
from psutil import pid_exists
from pwd import getpwnam
from subprocess import Popen, PIPE
from time import sleep

from vyos import ConfigError
from vyos.config import Config
from vyos.ifconfig import Interface
from vyos.validate import is_addr_assigned

user = 'openvpn'
group = 'openvpn'

# Please be careful if you edit the template.
config_tmpl = """
### Autogenerated by interfaces-openvpn.py ###
#
# See https://community.openvpn.net/openvpn/wiki/Openvpn24ManPage
# for individual keyword definition

{% if description %}
# {{ description }}
{% endif %}

verb 3
status /opt/vyatta/etc/openvpn/status/{{ intf }}.status 30
writepid /var/run/openvpn/{{ intf }}.pid

dev-type {{ type }}
dev {{ intf }}
user {{ uid }}
group {{ gid }}
persist-key
iproute /usr/libexec/vyos/system/unpriv-ip

proto {% if 'tcp-active' in protocol -%}tcp-client{% elif 'tcp-passive' in protocol -%}tcp-server{% else %}udp{% endif %}

{%- if local_host %}
local {{ local_host }}
{% endif %}

{%- if local_port %}
lport {{ local_port }}
{% endif %}

{%- if remote_port %}
rport {{ remote_port }}
{% endif %}

{%- if remote_host %}
{% for remote in remote_host -%}
remote {{ remote }}
{% endfor -%}
{% endif %}

{%- if shared_secret_file %}
secret {{ shared_secret_file }}
{% endif %}

{%- if persistent_tunnel %}
persist-tun
{% endif %}

{%- if mode %}
{%- if 'client' in mode %}
#
# OpenVPN Client mode
#
client
nobind
{%- elif 'server' in mode %}
#
# OpenVPN Server mode
#
mode server
tls-server
keepalive {{ ping_interval }} {{ ping_restart }}
management /tmp/openvpn-mgmt-intf unix

{%- if server_topology %}
topology {% if 'point-to-point' in server_topology %}p2p{% else %}subnet{% endif %}
{% endif %}

{% for ns in server_dns_nameserver -%}
push "dhcp-option DNS {{ ns }}"
{% endfor -%}

{% for route in server_push_route -%}
push "route {{ route }}"
{% endfor -%}

{%- if server_domain %}
push "dhcp-option DOMAIN {{ server_domain }}"
{% endif %}

{%- if server_max_conn %}
max-clients {{ server_max_conn }}
{% endif %}

{%- if bridge_member %}
server-bridge nogw
{%- else %}
server {{ server_subnet }}
{% endif %}

{%- if server_reject_unconfigured %}
ccd-exclusive
{% endif %}

{%- else %}
#
# OpenVPN site-2-site mode
#
ping {{ ping_interval }}
ping-restart {{ ping_restart }}

{%- if local_address_subnet %}
ifconfig {{ local_address }} {{ local_address_subnet }}
{% elif remote_address %}
ifconfig {{ local_address }} {{ remote_address }}
{% endif %}

{% endif %}
{% endif %}

{%- if tls_ca_cert %}
ca {{ tls_ca_cert }}
{% endif %}

{%- if tls_cert %}
cert {{ tls_cert }}
{% endif %}

{%- if tls_key %}
key {{ tls_key }}
{% endif %}

{%- if tls_crypt %}
tls-crypt {{ tls_crypt }}
{% endif %}

{%- if tls_crl %}
crl-verify {{ tls_crl }}
{% endif %}

{%- if tls_version_min %}
tls-version-min {{tls_version_min}}
{% endif %}

{%- if tls_dh %}
dh {{ tls_dh }}
{% endif %}

{%- if tls_auth %}
tls-auth {{tls_auth}}
{% endif %}

{%- if 'active' in tls_role %}
tls-client
{%- elif 'passive' in tls_role %}
tls-server
{% endif %}

{%- if redirect_gateway %}
push "redirect-gateway {{ redirect_gateway }}"
{% endif %}

{%- if compress_lzo %}
compress lzo
{% endif %}

{%- if hash %}
auth {{ hash }}
{% endif %}

{%- if encryption %}
{%- if 'des' in encryption %}
cipher des-cbc
{%- elif '3des' in encryption %}
cipher des-ede3-cbc
{%- elif 'bf128' in encryption %}
cipher bf-cbc
keysize 128
{%- elif 'bf256' in encryption %}
cipher bf-cbc
keysize 25
{%- elif 'aes128gcm' in encryption %}
cipher aes-128-gcm
{%- elif 'aes128' in encryption %}
cipher aes-128-cbc
{%- elif 'aes192gcm' in encryption %}
cipher aes-192-gcm
{%- elif 'aes192' in encryption %}
cipher aes-192-cbc
{%- elif 'aes256gcm' in encryption %}
cipher aes-256-gcm
{%- elif 'aes256' in encryption %}
cipher aes-256-cbc
{% endif %}
{% endif %}

{%- if ncp_ciphers %}
ncp-ciphers {{ncp_ciphers}}
{% endif %}
{%- if disable_ncp %}
ncp-disable
{% endif %}

{%- if auth %}
auth-user-pass /tmp/openvpn-{{ intf }}-pw
auth-retry nointeract
{% endif %}

{%- if client %}
client-config-dir /opt/vyatta/etc/openvpn/ccd/{{ intf }}
{% endif %}

# DEPRECATED This option will be removed in OpenVPN 2.5
# Until OpenVPN v2.3 the format of the X.509 Subject fields was formatted like this:
# /C=US/L=Somewhere/CN=John Doe/emailAddress=john@example.com In addition the old
# behaviour was to remap any character other than alphanumeric, underscore ('_'),
# dash ('-'), dot ('.'), and slash ('/') to underscore ('_'). The X.509 Subject
# string as returned by the tls_id environmental variable, could additionally
# contain colon (':') or equal ('='). When using the --compat-names option, this
# old formatting and remapping will be re-enabled again. This is purely implemented
# for compatibility reasons when using older plug-ins or scripts which does not
# handle the new formatting or UTF-8 characters.
#
# See https://phabricator.vyos.net/T1512
compat-names

{% for option in options -%}
{{ option }}
{% endfor -%}
"""

client_tmpl = """
### Autogenerated by interfaces-openvpn.py ###

ifconfig-push {{ ip }} {{ remote_netmask }}
{% for route in push_route -%}
push "route {{ route }}"
{% endfor -%}

{% for net in subnet -%}
iroute {{ net }}
{% endfor -%}

{%- if disable %}
disable
{% endif %}
"""

default_config_data = {
    'address': [],
    'auth_user': '',
    'auth_pass': '',
    'auth': False,
    'bridge_member': [],
    'compress_lzo': False,
    'deleted': False,
    'description': '',
    'disable': False,
    'disable_ncp': False,
    'encryption': '',
    'hash': '',
    'intf': '',
    'ping_restart': '60',
    'ping_interval': '10',
    'local_address': '',
    'local_address_subnet': '',
    'local_host': '',
    'local_port': '',
    'mode': '',
    'ncp_ciphers': '',
    'options': [],
    'persistent_tunnel': False,
    'protocol': '',
    'redirect_gateway': '',
    'remote_address': '',
    'remote_host': [],
    'remote_port': '',
    'client': [],
    'server_domain': '',
    'server_max_conn': '',
    'server_dns_nameserver': [],
    'server_push_route': [],
    'server_reject_unconfigured': False,
    'server_subnet': '',
    'server_topology': '',
    'shared_secret_file': '',
    'tls': False,
    'tls_auth': '',
    'tls_ca_cert': '',
    'tls_cert': '',
    'tls_crl': '',
    'tls_dh': '',
    'tls_key': '',
    'tls_crypt': '',
    'tls_role': '',
    'tls_version_min': '',
    'type': 'tun',
    'uid': user,
    'gid': group,
}

def subprocess_cmd(command):
    p = Popen(command, stdout=PIPE, shell=True)
    p.communicate()

def get_config_name(intf):
    cfg_file = r'/opt/vyatta/etc/openvpn/openvpn-{}.conf'.format(intf)
    return cfg_file

def openvpn_mkdir(directory):
    # create directory on demand
    if not os.path.exists(directory):
        os.mkdir(directory)

    # fix permissions - corresponds to mode 755
    os.chmod(directory, S_IRWXU|S_IRGRP|S_IXGRP|S_IROTH|S_IXOTH)
    uid = getpwnam(user).pw_uid
    gid = getgrnam(group).gr_gid
    os.chown(directory, uid, gid)

def fixup_permission(filename, permission=S_IRUSR):
    """
    Check if the given file exists and change ownershit to root/vyattacfg
    and appripriate file access permissions - default is user and group readable
    """
    if os.path.isfile(filename):
        os.chmod(filename, permission)

        # make file owned by root / vyattacfg
        uid = getpwnam('root').pw_uid
        gid = getgrnam('vyattacfg').gr_gid
        os.chown(filename, uid, gid)

def checkCertHeader(header, filename):
    """
    Verify if filename contains specified header.
    Returns True on success or on file not found to not trigger the exceptions
    """
    if not os.path.isfile(filename):
        return False

    with open(filename, 'r') as f:
        for line in f:
            if re.match(header, line):
                return True

    return True

def get_config():
    openvpn = deepcopy(default_config_data)
    conf = Config()

    # determine tagNode instance
    if 'VYOS_TAGNODE_VALUE' not in os.environ:
        raise ConfigError('Interface (VYOS_TAGNODE_VALUE) not specified')

    openvpn['intf'] = os.environ['VYOS_TAGNODE_VALUE']

    # Check if interface instance has been removed
    if not conf.exists('interfaces openvpn ' + openvpn['intf']):
        openvpn['deleted'] = True
        return openvpn

    # Check if we belong to any bridge interface
    for bridge in conf.list_nodes('interfaces bridge'):
        for intf in conf.list_nodes('interfaces bridge {} member interface'.format(bridge)):
            if intf == openvpn['intf']:
                openvpn['bridge_member'].append(intf)

    # set configuration level
    conf.set_level('interfaces openvpn ' + openvpn['intf'])

    # retrieve authentication options - username
    if conf.exists('authentication username'):
        openvpn['auth_user'] = conf.return_value('authentication username')
        openvpn['auth'] = True

    # retrieve authentication options - username
    if conf.exists('authentication password'):
        openvpn['auth_pass'] = conf.return_value('authentication password')
        openvpn['auth'] = True

    # retrieve interface description
    if conf.exists('description'):
        openvpn['description'] = conf.return_value('description')

    # interface device-type
    if conf.exists('device-type'):
        openvpn['type'] = conf.return_value('device-type')

    # disable interface
    if conf.exists('disable'):
        openvpn['disable'] = True

    # data encryption algorithm cipher
    if conf.exists('encryption cipher'):
        openvpn['encryption'] = conf.return_value('encryption cipher')

    # disable ncp-ciphers support
    if conf.exists('encryption disable-ncp'):
        openvpn['disable_ncp'] = True

    # data encryption algorithm ncp-list
    if conf.exists('encryption ncp-ciphers'):
        _ncp_ciphers = []
        for enc in conf.return_values('encryption ncp-ciphers'):
            if enc == 'des':
                _ncp_ciphers.append('des-cbc')
                _ncp_ciphers.append('DES-CBC')
            elif enc == '3des':
                _ncp_ciphers.append('des-ede3-cbc')
                _ncp_ciphers.append('DES-EDE3-CBC')
            elif enc == 'aes128':
                _ncp_ciphers.append('aes-128-cbc')
                _ncp_ciphers.append('AES-128-CBC')
            elif enc == 'aes128gcm':
                _ncp_ciphers.append('aes-128-gcm')
                _ncp_ciphers.append('AES-128-GCM')
            elif enc == 'aes192':
                _ncp_ciphers.append('aes-192-cbc')
                _ncp_ciphers.append('AES-192-CBC')
            elif enc == 'aes192gcm':
                _ncp_ciphers.append('aes-192-gcm')
                _ncp_ciphers.append('AES-192-GCM')
            elif enc == 'aes256':
                _ncp_ciphers.append('aes-256-cbc')
                _ncp_ciphers.append('AES-256-CBC')
            elif enc == 'aes256gcm':
                _ncp_ciphers.append('aes-256-gcm')
                _ncp_ciphers.append('AES-256-GCM')
        openvpn['ncp_ciphers'] = ':'.join(_ncp_ciphers)

    # hash algorithm
    if conf.exists('hash'):
        openvpn['hash'] = conf.return_value('hash')

    # Maximum number of keepalive packet failures
    if conf.exists('keep-alive failure-count') and conf.exists('keep-alive interval'):
        fail_count = conf.return_value('keep-alive failure-count')
        interval = conf.return_value('keep-alive interval')
        openvpn['ping_interval' ] = interval
        openvpn['ping_restart' ] = int(interval) * int(fail_count)

    # Local IP address of tunnel - even as it is a tag node - we can only work
    # on the first address
    if conf.exists('local-address'):
        openvpn['local_address'] = conf.list_nodes('local-address')[0]
        if conf.exists('local-address {} subnet-mask'.format(openvpn['local_address'])):
            openvpn['local_address_subnet'] = conf.return_value('local-address {} subnet-mask'.format(openvpn['local_address']))

    # Local IP address to accept connections
    if conf.exists('local-host'):
        openvpn['local_host'] = conf.return_value('local-host')

    # Local port number to accept connections
    if conf.exists('local-port'):
        openvpn['local_port'] = conf.return_value('local-port')

    # OpenVPN operation mode
    if conf.exists('mode'):
        mode = conf.return_value('mode')
        openvpn['mode'] = mode

    # Additional OpenVPN options
    if conf.exists('openvpn-option'):
        openvpn['options'] = conf.return_values('openvpn-option')

    # Do not close and reopen interface
    if conf.exists('persistent-tunnel'):
        openvpn['persistent_tunnel'] = True

    # Communication protocol
    if conf.exists('protocol'):
        openvpn['protocol'] = conf.return_value('protocol')

    # IP address of remote end of tunnel
    if conf.exists('remote-address'):
        openvpn['remote_address'] = conf.return_value('remote-address')

    # Remote host to connect to (dynamic if not set)
    if conf.exists('remote-host'):
        openvpn['remote_host'] = conf.return_values('remote-host')

    # Remote port number to connect to
    if conf.exists('remote-port'):
        openvpn['remote_port'] = conf.return_value('remote-port')

    # OpenVPN tunnel to be used as the default route
    # see https://openvpn.net/community-resources/reference-manual-for-openvpn-2-4/
    # redirect-gateway flags
    if conf.exists('replace-default-route'):
        openvpn['redirect_gateway'] = 'def1'

    if conf.exists('replace-default-route local'):
        openvpn['redirect_gateway'] = 'local def1'

    # Topology for clients
    if conf.exists('server topology'):
        openvpn['server_topology'] = conf.return_value('server topology')

    # Server-mode subnet (from which client IPs are allocated)
    if conf.exists('server subnet'):
        network = conf.return_value('server subnet')
        tmp = IPv4Interface(network).with_netmask
        # convert the network in format: "192.0.2.0 255.255.255.0" for later use in template
        openvpn['server_subnet'] = tmp.replace(r'/', ' ')

    # Client-specific settings
    for client in conf.list_nodes('server client'):
        # set configuration level
        conf.set_level('interfaces openvpn ' + openvpn['intf'] + ' server client ' + client)
        data = {
            'name': client,
            'disable': False,
            'ip': '',
            'push_route': [],
            'subnet': [],
            'remote_netmask': ''
        }

        # note: with "topology subnet", this is "<ip> <netmask>".
        #       with "topology p2p", this is "<ip> <our_ip>".
        if openvpn['server_topology'] == 'subnet':
            # we are only interested in the netmask portion of server_subnet
            data['remote_netmask'] = openvpn['server_subnet'].split(' ')[1]
        else:
            # we need the server subnet in format 192.0.2.0/255.255.255.0
            subnet = openvpn['server_subnet'].replace(' ', r'/')
            # get iterator over the usable hosts in the network
            tmp = ip_network(subnet).hosts()
            # OpenVPN always uses the subnets first available IP address
            data['remote_netmask'] = list(tmp)[0]

        # Option to disable client connection
        if conf.exists('disable'):
            data['disable'] = True

        # IP address of the client
        if conf.exists('ip'):
            data['ip'] = conf.return_value('ip')

        # Route to be pushed to the client
        for network in conf.return_values('push-route'):
            tmp = IPv4Interface(network).with_netmask
            data['push_route'].append(tmp.replace(r'/', ' '))

        # Subnet belonging to the client
        for network in conf.return_values('subnet'):
            tmp = IPv4Interface(network).with_netmask
            data['subnet'].append(tmp.replace(r'/', ' '))

        # Append to global client list
        openvpn['client'].append(data)

    # re-set configuration level
    conf.set_level('interfaces openvpn ' + openvpn['intf'])

    # DNS suffix to be pushed to all clients
    if conf.exists('server domain-name'):
        openvpn['server_domain'] = conf.return_value('server domain-name')

    # Number of maximum client connections
    if conf.exists('server max-connections'):
        openvpn['server_max_conn'] = conf.return_value('server max-connections')

    # Domain Name Server (DNS)
    if conf.exists('server name-server'):
        openvpn['server_dns_nameserver'] = conf.return_values('server name-server')

    # Route to be pushed to all clients
    if conf.exists('server push-route'):
        for network in conf.return_values('server push-route'):
            tmp = IPv4Interface(network).with_netmask
            openvpn['server_push_route'].append(tmp.replace(r'/', ' '))

    # Reject connections from clients that are not explicitly configured
    if conf.exists('server reject-unconfigured-clients'):
        openvpn['server_reject_unconfigured'] = True

    # File containing TLS auth static key
    if conf.exists('tls auth-file'):
        openvpn['tls_auth'] = conf.return_value('tls auth-file')
        openvpn['tls'] = True

    # File containing certificate for Certificate Authority (CA)
    if conf.exists('tls ca-cert-file'):
         openvpn['tls_ca_cert'] = conf.return_value('tls ca-cert-file')
         openvpn['tls'] = True

    # File containing certificate for this host
    if conf.exists('tls cert-file'):
         openvpn['tls_cert'] = conf.return_value('tls cert-file')
         openvpn['tls'] = True

    # File containing certificate revocation list (CRL) for this host
    if conf.exists('tls crl-file'):
         openvpn['tls_crl'] = conf.return_value('tls crl-file')
         openvpn['tls'] = True

    # File containing Diffie Hellman parameters (server only)
    if conf.exists('tls dh-file'):
         openvpn['tls_dh'] = conf.return_value('tls dh-file')
         openvpn['tls'] = True

    # File containing this host's private key
    if conf.exists('tls key-file'):
         openvpn['tls_key'] = conf.return_value('tls key-file')
         openvpn['tls'] = True

    # File containing key to encrypt control channel packets
    if conf.exists('tls crypt-file'):
         openvpn['tls_crypt'] = conf.return_value('tls crypt-file')
         openvpn['tls'] = True

    # Role in TLS negotiation
    if conf.exists('tls role'):
         openvpn['tls_role'] = conf.return_value('tls role')
         openvpn['tls'] = True

    # Minimum required TLS version
    if conf.exists('tls tls-version-min'):
         openvpn['tls_version_min'] = conf.return_value('tls tls-version-min')

    if conf.exists('shared-secret-key-file'):
        openvpn['shared_secret_file'] = conf.return_value('shared-secret-key-file')

    if conf.exists('use-lzo-compression'):
        openvpn['compress_lzo'] = True

    # Special case when using EC certificates:
    # if key-file is EC and dh-file is unset, set tls_dh to 'none'
    if not openvpn['tls_dh'] and openvpn['tls_key'] and checkCertHeader('-----BEGIN EC PRIVATE KEY-----', openvpn['tls_key']):
        openvpn['tls_dh'] = 'none'

    return openvpn

def verify(openvpn):
    if openvpn['deleted']:
        return None

    if not openvpn['mode']:
        raise ConfigError('Must specify OpenVPN operation mode')

    # Checks which need to be performed on interface rmeoval
    if openvpn['deleted']:
        # OpenVPN interface can not be deleted if it's still member of a bridge
        if openvpn['bridge_member']:
            raise ConfigError('Can not delete {} as it is a member interface of bridge {}!'.format(openvpn['intf'], bridge))

    # Check if we have disabled ncp and at the same time specified ncp-ciphers
    if openvpn['disable_ncp'] and openvpn['ncp_ciphers']:
        raise ConfigError('Cannot specify both "encryption disable-ncp" and "encryption ncp-ciphers"')
    #
    # OpenVPN client mode - VERIFY
    #
    if openvpn['mode'] == 'client':
        if openvpn['local_port']:
            raise ConfigError('Cannot specify "local-port" in client mode')

        if openvpn['local_host']:
            raise ConfigError('Cannot specify "local-host" in client mode')

        if openvpn['protocol'] == 'tcp-passive':
            raise ConfigError('Protocol "tcp-passive" is not valid in client mode')

        if not openvpn['remote_host']:
            raise ConfigError('Must specify "remote-host" in client mode')

        if openvpn['tls_dh'] and openvpn['tls_dh'] != 'none':
            raise ConfigError('Cannot specify "tls dh-file" in client mode')

    #
    # OpenVPN site-to-site - VERIFY
    #
    if openvpn['mode'] == 'site-to-site':
        if not (openvpn['local_address'] or openvpn['bridge_member']):
            raise ConfigError('Must specify "local-address" or "bridge member interface"')

        for host in openvpn['remote_host']:
            if host == openvpn['remote_address']:
                raise ConfigError('"remote-address" cannot be the same as "remote-host"')

        if openvpn['type'] == 'tun':
            if not openvpn['remote_address']:
                raise ConfigError('Must specify "remote-address"')

            if openvpn['local_address'] == openvpn['remote_address']:
                raise ConfigError('"local-address" and "remote-address" cannot be the same')

            if openvpn['local_address'] == openvpn['local_host']:
                raise ConfigError('"local-address" cannot be the same as "local-host"')

        if openvpn['ncp_ciphers']:
            raise ConfigError('encryption ncp-ciphers cannot be specified in site-to-site mode, only server or client')

    else:
        if openvpn['local_address'] or openvpn['remote_address']:
            raise ConfigError('Cannot specify "local-address" or "remote-address" in client-server mode')

        elif openvpn['bridge_member']:
            raise ConfigError('Cannot specify "local-address" or "remote-address" in bridge mode')

    #
    # OpenVPN server mode - VERIFY
    #
    if openvpn['mode'] == 'server':
        if openvpn['protocol'] == 'tcp-active':
            raise ConfigError('Protocol "tcp-active" is not valid in server mode')

        if openvpn['remote_port']:
            raise ConfigError('Cannot specify "remote-port" in server mode')

        if openvpn['remote_host']:
            raise ConfigError('Cannot specify "remote-host" in server mode')

        if openvpn['protocol'] == 'tcp-passive' and len(openvpn['remote_host']) > 1:
            raise ConfigError('Cannot specify more than 1 "remote-host" with "tcp-passive"')

        if not openvpn['tls_dh'] and not checkCertHeader('-----BEGIN EC PRIVATE KEY-----', openvpn['tls_key']):
            raise ConfigError('Must specify "tls dh-file" when not using EC keys in server mode')

        if not openvpn['server_subnet']:
            if not openvpn['bridge_member']:
                raise ConfigError('Must specify "server subnet" option in server mode')

    else:
        # checks for both client and site-to-site go here
        if openvpn['server_reject_unconfigured']:
            raise ConfigError('reject-unconfigured-clients is only supported in OpenVPN server mode')

        if openvpn['server_topology']:
            raise ConfigError('The "topology" option is only valid in server mode')

        if (not openvpn['remote_host']) and openvpn['redirect_gateway']:
            raise ConfigError('Cannot set "replace-default-route" without "remote-host"')

    #
    # OpenVPN common verification section
    # not depending on any operation mode
    #

    # verify specified IP address is present on any interface on this system
    if openvpn['local_host']:
        if not is_addr_assigned(openvpn['local_host']):
            raise ConfigError('No interface on system with specified local-host IP address: {}'.format(openvpn['local_host']))

    # TCP active
    if openvpn['protocol'] == 'tcp-active':
        if openvpn['local_port']:
            raise ConfigError('Cannot specify "local-port" with "tcp-active"')

        if not openvpn['remote_host']:
            raise ConfigError('Must specify "remote-host" with "tcp-active"')

    # shared secret and TLS
    if not (openvpn['shared_secret_file'] or openvpn['tls']):
        raise ConfigError('Must specify one of "shared-secret-key-file" and "tls"')

    if openvpn['shared_secret_file'] and openvpn['tls']:
        raise ConfigError('Can only specify one of "shared-secret-key-file" and "tls"')

    if openvpn['mode'] in ['client', 'server']:
        if not openvpn['tls']:
            raise ConfigError('Must specify "tls" in client-server mode')

    #
    # TLS/encryption
    #
    if openvpn['shared_secret_file']:
        if openvpn['encryption'] in ['aes128gcm', 'aes192gcm', 'aes256gcm']:
            raise ConfigError('GCM encryption with shared-secret-key-file is not supported')

        if not checkCertHeader('-----BEGIN OpenVPN Static key V1-----', openvpn['shared_secret_file']):
            raise ConfigError('Specified shared-secret-key-file "{}" is not valid'.format(openvpn['shared_secret_file']))

    if openvpn['tls']:
        if not openvpn['tls_ca_cert']:
            raise ConfigError('Must specify "tls ca-cert-file"')

        if not (openvpn['mode'] == 'client' and openvpn['auth']):
            if not openvpn['tls_cert']:
                raise ConfigError('Must specify "tls cert-file"')

            if not openvpn['tls_key']:
                raise ConfigError('Must specify "tls key-file"')

        if openvpn['tls_auth'] and openvpn['tls_crypt']:
            raise ConfigError('TLS auth and crypt are mutually exclusive')

        if not checkCertHeader('-----BEGIN CERTIFICATE-----', openvpn['tls_ca_cert']):
            raise ConfigError('Specified ca-cert-file "{}" is invalid'.format(openvpn['tls_ca_cert']))

        if openvpn['tls_auth']:
            if not checkCertHeader('-----BEGIN OpenVPN Static key V1-----', openvpn['tls_auth']):
                raise ConfigError('Specified auth-file "{}" is invalid'.format(openvpn['tls_auth']))

        if openvpn['tls_cert']:
            if not checkCertHeader('-----BEGIN CERTIFICATE-----', openvpn['tls_cert']):
                raise ConfigError('Specified cert-file "{}" is invalid'.format(openvpn['tls_cert']))

        if openvpn['tls_key']:
            if not checkCertHeader('-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', openvpn['tls_key']):
                raise ConfigError('Specified key-file "{}" is not valid'.format(openvpn['tls_key']))

        if openvpn['tls_crypt']:
            if not checkCertHeader('-----BEGIN OpenVPN Static key V1-----', openvpn['tls_crypt']):
                raise ConfigError('Specified TLS crypt-file "{}" is invalid'.format(openvpn['tls_crypt']))

        if openvpn['tls_crl']:
            if not checkCertHeader('-----BEGIN X509 CRL-----', openvpn['tls_crl']):
                raise ConfigError('Specified crl-file "{} not valid'.format(openvpn['tls_crl']))

        if openvpn['tls_dh'] and openvpn['tls_dh'] != 'none':
            if not checkCertHeader('-----BEGIN DH PARAMETERS-----', openvpn['tls_dh']):
                raise ConfigError('Specified dh-file "{}" is not valid'.format(openvpn['tls_dh']))

        if openvpn['tls_role']:
            if openvpn['mode'] in ['client', 'server']:
                if not openvpn['tls_auth']:
                    raise ConfigError('Cannot specify "tls role" in client-server mode')

            if openvpn['tls_role'] == 'active':
                if openvpn['protocol'] == 'tcp-passive':
                    raise ConfigError('Cannot specify "tcp-passive" when "tls role" is "active"')

                if openvpn['tls_dh'] and openvpn['tls_dh'] != 'none':
                    raise ConfigError('Cannot specify "tls dh-file" when "tls role" is "active"')

            elif openvpn['tls_role'] == 'passive':
                if openvpn['protocol'] == 'tcp-active':
                    raise ConfigError('Cannot specify "tcp-active" when "tls role" is "passive"')

                if not openvpn['tls_dh']:
                    raise ConfigError('Must specify "tls dh-file" when "tls role" is "passive"')

        if openvpn['tls_key'] and checkCertHeader('-----BEGIN EC PRIVATE KEY-----', openvpn['tls_key']):
            if openvpn['tls_dh'] and openvpn['tls_dh'] != 'none':
                print('Warning: using dh-file and EC keys simultaneously will lead to DH ciphers being used instead of ECDH')
            else:
                print('Diffie-Hellman prime file is unspecified, assuming ECDH')

    #
    # Auth user/pass
    #
    if openvpn['auth']:
        if not openvpn['auth_user']:
            raise ConfigError('Username for authentication is missing')

        if not openvpn['auth_pass']:
            raise ConfigError('Password for authentication is missing')

    #
    # Client
    #
    subnet = openvpn['server_subnet'].replace(' ', '/')
    for client in openvpn['client']:
        if not ip_address(client['ip']) in ip_network(subnet):
            raise ConfigError('Client IP "{}" not in server subnet "{}'.format(client['ip'], subnet))



    return None

def generate(openvpn):
    if openvpn['deleted'] or openvpn['disable']:
        return None

    interface = openvpn['intf']
    directory = os.path.dirname(get_config_name(interface))

    # create config directory on demand
    openvpn_mkdir(directory)
    # create status directory on demand
    openvpn_mkdir(directory + '/status')
    # create client config dir on demand
    openvpn_mkdir(directory + '/ccd')
    # crete client config dir per interface on demand
    openvpn_mkdir(directory + '/ccd/' + interface)

    # Fix file permissons for keys
    fixup_permission(openvpn['shared_secret_file'])
    fixup_permission(openvpn['tls_key'])

    # Generate User/Password authentication file
    if openvpn['auth']:
        auth_file = '/tmp/openvpn-{}-pw'.format(interface)
        with open(auth_file, 'w') as f:
            f.write('{}\n{}'.format(openvpn['auth_user'], openvpn['auth_pass']))

        fixup_permission(auth_file)

    # get numeric uid/gid
    uid = getpwnam(user).pw_uid
    gid = getgrnam(group).gr_gid

    # Generate client specific configuration
    for client in openvpn['client']:
        client_file = directory + '/ccd/' + interface + '/' + client['name']
        tmpl = Template(client_tmpl)
        client_text = tmpl.render(client)
        with open(client_file, 'w') as f:
            f.write(client_text)
        os.chown(client_file, uid, gid)

    tmpl = Template(config_tmpl)
    config_text = tmpl.render(openvpn)

    # we need to support quoting of raw parameters from OpenVPN CLI
    # see https://phabricator.vyos.net/T1632
    config_text = config_text.replace("&quot;",'"')

    with open(get_config_name(interface), 'w') as f:
        f.write(config_text)
    os.chown(get_config_name(interface), uid, gid)

    return None

def apply(openvpn):
    pid = 0
    pidfile = '/var/run/openvpn/{}.pid'.format(openvpn['intf'])
    if os.path.isfile(pidfile):
        pid = 0
        with open(pidfile, 'r') as f:
            pid = int(f.read())

    # Always stop OpenVPN service. We can not send a SIGUSR1 for restart of the
    # service as the configuration is not re-read. Stop daemon only if it's
    # running - it could have died or killed by someone evil
    if pid_exists(pid):
        cmd  = 'start-stop-daemon --stop --quiet'
        cmd += ' --pidfile ' + pidfile
        subprocess_cmd(cmd)

    # cleanup old PID file
    if os.path.isfile(pidfile):
        os.remove(pidfile)

    # Do some cleanup when OpenVPN is disabled/deleted
    if openvpn['deleted'] or openvpn['disable']:
        # cleanup old configuration file
        if os.path.isfile(get_config_name(openvpn['intf'])):
            os.remove(get_config_name(openvpn['intf']))

        # cleanup client config dir
        directory = os.path.dirname(get_config_name(openvpn['intf']))
        if os.path.isdir(directory + '/ccd/' + openvpn['intf']):
            try:
                os.remove(directory + '/ccd/' + openvpn['intf'] + '/*')
            except:
                pass

        return None

    # On configuration change we need to wait for the 'old' interface to
    # vanish from the Kernel, if it is not gone, OpenVPN will report:
    # ERROR: Cannot ioctl TUNSETIFF vtun10: Device or resource busy (errno=16)
    while openvpn['intf'] in interfaces():
        sleep(0.250) # 250ms

    # No matching OpenVPN process running - maybe it got killed or none
    # existed - nevertheless, spawn new OpenVPN process
    cmd  = 'start-stop-daemon --start --quiet'
    cmd += ' --pidfile ' + pidfile
    cmd += ' --exec /usr/sbin/openvpn'
    # now pass arguments to openvpn binary
    cmd += ' --'
    cmd += ' --daemon openvpn-' + openvpn['intf']
    cmd += ' --config ' + get_config_name(openvpn['intf'])

    # execute assembled command
    subprocess_cmd(cmd)

    # better late then sorry ... but we can only set interface alias after
    # OpenVPN has been launched and created the interface
    cnt = 0
    while openvpn['intf'] not in interfaces():
        # If VPN tunnel can't be established because the peer/server isn't
        # (temporarily) available, the vtun interface never becomes registered
        # with the kernel, and the commit would hang if there is no bail out
        # condition
        cnt += 1
        if cnt == 50:
            break

        # sleep 250ms
        sleep(0.250)

    try:
        # we need to catch the exception if the interface is not up due to
        # reason stated above
        Interface(openvpn['intf']).set_alias(openvpn['description'])
    except:
        pass

    # TAP interface needs to be brought up explicitly
    if openvpn['type'] == 'tap':
        if not openvpn['disable']:
            Interface(openvpn['intf']).set_state('up')

    return None


if __name__ == '__main__':
    try:
        c = get_config()
        verify(c)
        generate(c)
        apply(c)
    except ConfigError as e:
        print(e)
        exit(1)
