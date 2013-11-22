# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo.config import cfg

from cloudbaseinit.openstack.common import log as logging
from cloudbaseinit.osutils import factory as osutils_factory
from cloudbaseinit.plugins import base

LOG = logging.getLogger(__name__)

opts = [
    cfg.StrOpt('network_adapter', default=None, help='Network adapter to '
               'configure. If not specified, the first available ethernet '
               'adapter will be chosen'),
]

CONF = cfg.CONF
CONF.register_opts(opts)


class NetworkConfigPlugin(base.BasePlugin):

    def _parse_config(self, config):
        ifaces = []
        iface = {}
        ifname = None
        for line in config.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            (key, value) = line.split(None, 1)
            # iface stanza means beginning of interface config
            if key == 'iface':
                if iface:
                    ifaces.append(iface)
                (ifname, family, method) = value.split(None, 2)
                iface = {'name': ifname, 'family': family,
                         'method': method}
            elif key in ['address', 'netmask', 'boardcast', 'gateway',
                         'hwaddress']:
                iface[key] = value.strip()
            elif key in ['dns-nameservers', 'dns-search']:
                iface[key] = value.split()
            elif key in ['pre-up', 'up', 'down', 'post-down']:
                if key not in iface:
                    iface[key] = []
                iface[key].append(value)
        if iface:
            ifaces.append(iface)
        return ifaces

    def execute(self, service, shared_data):
        meta_data = service.get_meta_data('openstack')
        if 'network_config' not in meta_data:
            return (base.PLUGIN_EXECUTION_DONE, False)

        network_config = meta_data['network_config']
        if 'content_path' not in network_config:
            return (base.PLUGIN_EXECUTION_DONE, False)

        content_path = network_config['content_path']
        content_name = content_path.rsplit('/', 1)[-1]
        debian_network_conf = service.get_content('openstack', content_name)

        LOG.debug('network config content:\n%s' % debian_network_conf)
        ifaces = []
        for i in self._parse_config(debian_network_conf):
            # IPv4 support only
            if i['family'] not in ['inet']:
                LOG.debug('Skipping unsupported family: %s' % i['family'])
                continue
            if i['method'] not in ['static', 'manual', 'dhcp']:
                LOG.debug('Skipping unsupported method: %s' % i['method'])
                continue
            ifaces.append(i)

        osutils = osutils_factory.OSUtilsFactory().get_os_utils()

        if CONF.network_adapter:
            network_adapter_names = [CONF.network_adapter]
        else:
            # Get all available ones if none provided
            network_adapter_names = osutils.get_network_adapters()
            if not len(network_adapter_names):
                raise Exception("No network adapter available")

        reboot_required = False
        for adapter, iface in zip(network_adapter_names, ifaces):
            LOG.info('Configuring network adapter: \'%s\'' % adapter)
            if iface['method'] == 'static':
                reboot_required |= osutils.set_static_network_config(
                    adapter_name=adapter,
                    address=iface.get('address'),
                    netmask=iface.get('netmask'),
                    broadcast=iface.get('broadcast'),
                    gateway=iface.get('gateway'),
                    dnsnameservers=iface.get('dns-nameservers'))
            elif iface['method'] == 'dhcp':
                reboot_required |= osutils.set_dhcp_network_config(
                    adapter_name=adapter)
            elif iface['method'] == 'manual':
                pass

        return (base.PLUGIN_EXECUTION_DONE, reboot_required)
