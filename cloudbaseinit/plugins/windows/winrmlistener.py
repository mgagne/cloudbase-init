# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the 'License'); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an 'AS IS' BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo.config import cfg

from cloudbaseinit.openstack.common import log as logging
from cloudbaseinit.osutils import factory as osutils_factory
from cloudbaseinit.plugins import base
from cloudbaseinit.plugins.windows import x509
from cloudbaseinit.plugins.windows import winrmconfig

LOG = logging.getLogger(__name__)

opts = [
    cfg.BoolOpt('winrm_enable_basic_auth', default=True,
                help='Enables basic authentication for the WinRM '
                'HTTPS listener'),
]

CONF = cfg.CONF
CONF.register_opts(opts)

LOG = logging.getLogger(__name__)


class ConfigWinRMListenerPlugin(base.BasePlugin):
    _cert_subject = "CN=Cloudbase-Init WinRM"
    _winrm_service_name = "WinRM"

    def _check_winrm_service(self, osutils):
        if not osutils.check_service_exists(self._winrm_service_name):
            LOG.warn("Cannot configure the WinRM listener as the service "
                     "is not available")
            return False

        start_mode = osutils.get_service_start_mode(self._winrm_service_name)
        if start_mode in [osutils.SERVICE_START_MODE_MANUAL,
                          osutils.SERVICE_START_MODE_DISABLED]:
            # TODO(alexpilotti) Set to "Delayed Start"
            osutils.set_service_start_mode(
                self._winrm_service_name,
                osutils.SERVICE_START_MODE_AUTOMATIC)

        service_status = osutils.get_service_status(self._winrm_service_name)
        if service_status == osutils.SERVICE_STATUS_STOPPED:
            osutils.start_service(self._winrm_service_name)

        return True

    def execute(self, service, shared_data):
        osutils = osutils_factory.OSUtilsFactory().get_os_utils()

        if not self._check_winrm_service(osutils):
            return (base.PLUGIN_EXECUTE_ON_NEXT_BOOT, False)

        winrm_config = winrmconfig.WinRMConfig()
        winrm_config.set_auth_config(basic=CONF.winrm_enable_basic_auth)

        cert_manager = x509.CryptoAPICertManager()
        cert_thumbprint = cert_manager.create_self_signed_cert(
            self._cert_subject)

        protocol = winrmconfig.LISTENER_PROTOCOL_HTTPS

        if winrm_config.get_listener(protocol=protocol):
            winrm_config.delete_listener(protocol=protocol)

        winrm_config.create_listener(
            cert_thumbprint=cert_thumbprint,
            protocol=protocol)

        listener_config = winrm_config.get_listener(protocol=protocol)
        listener_port = listener_config.get("Port")

        rule_name = "WinRM %s" % protocol
        osutils.firewall_create_rule(rule_name, listener_port,
                                     osutils.PROTOCOL_TCP)

        return (base.PLUGIN_EXECUTION_DONE, False)
