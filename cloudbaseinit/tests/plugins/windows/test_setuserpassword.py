# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Cloudbase Solutions Srl
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

import mock
import unittest

from oslo.config import cfg

from cloudbaseinit.plugins import constants
from cloudbaseinit.plugins.windows import setuserpassword
from cloudbaseinit.tests.metadata import fake_json_response

CONF = cfg.CONF


class SetUserPasswordPluginTests(unittest.TestCase):

    def setUp(self):
        self._setpassword_plugin = setuserpassword.SetUserPasswordPlugin()
        self.fake_data = fake_json_response.get_fake_metadata_json(
            '2013-04-04')

    @mock.patch('base64.b64encode')
    @mock.patch('cloudbaseinit.utils.crypt.CryptManager'
                '.load_ssh_rsa_public_key')
    def test_encrypt_password(self, mock_load_ssh_key, mock_b64encode):
        mock_rsa = mock.MagicMock()
        fake_ssh_pub_key = 'fake key'
        fake_password = 'fake password'
        mock_load_ssh_key.return_value = mock_rsa
        mock_rsa.__enter__().public_encrypt.return_value = 'public encrypted'
        mock_b64encode.return_value = 'encrypted password'

        response = self._setpassword_plugin._encrypt_password(
            fake_ssh_pub_key, fake_password)
        print mock_rsa.mock_calls

        mock_load_ssh_key.assert_called_with(fake_ssh_pub_key)
        mock_rsa.__enter__().public_encrypt.assert_called_with('fake password')
        mock_b64encode.assert_called_with('public encrypted')
        self.assertEqual(response, 'encrypted password')

    def _test_get_ssh_public_key(self, data_exists):
        mock_service = mock.MagicMock()
        mock_service.get_meta_data.return_value = self.fake_data
        if data_exists is False:
            del self.fake_data['public_keys']
            response = self._setpassword_plugin._get_ssh_public_key(
                mock_service)
            self.assertEqual(response, False)
        else:
            response = self._setpassword_plugin._get_ssh_public_key(
                mock_service)
            mock_service.get_meta_data.assert_called_with(
                'openstack', self._setpassword_plugin._post_password_md_ver)
            self.assertEqual(response, self.fake_data['public_keys']['name'])

    def test_get_ssh_plublic_key(self):
        self._test_get_ssh_public_key(data_exists=True)

    def test_get_ssh_plublic_key_no_pub_keys(self):
        self._test_get_ssh_public_key(data_exists=False)

    def test_get_password(self):
        mock_service = mock.MagicMock()
        mock_osutils = mock.MagicMock()
        mock_service.get_meta_data.return_value = self.fake_data
        CONF.set_override('inject_user_password', False)
        mock_osutils.generate_random_password.return_value = 'Passw0rd'
        response = self._setpassword_plugin._get_password(mock_service,
                                                          mock_osutils)
        mock_service.get_meta_data.assert_called_with('openstack')
        mock_osutils.generate_random_password.assert_called_once_with(14)
        self.assertEqual(response, 'Passw0rd')

    @mock.patch('cloudbaseinit.plugins.windows.setuserpassword.'
                'SetUserPasswordPlugin._get_ssh_public_key')
    @mock.patch('cloudbaseinit.plugins.windows.setuserpassword.'
                'SetUserPasswordPlugin._encrypt_password')
    def _test_set_metadata_password(self, mock_encrypt_password,
                                    mock_get_key, ssh_pub_key):
        fake_passw0rd = 'fake Passw0rd'
        mock_service = mock.MagicMock()
        mock_get_key.return_value = ssh_pub_key
        mock_encrypt_password.return_value = 'encrypted password'
        mock_service.post_password.return_value = 'value'

        response = self._setpassword_plugin._set_metadata_password(
            fake_passw0rd, mock_service)

        if ssh_pub_key is None:
            self.assertEqual(response, True)
        else:
            mock_get_key.assert_called_once_with(mock_service)
            mock_encrypt_password.assert_called_once_with(ssh_pub_key,
                                                          fake_passw0rd)
            mock_service.post_password.assert_called_with(
                'encrypted password',
                self._setpassword_plugin._post_password_md_ver)
            self.assertEqual(response, 'value')

    def test_set_metadata_password_with_ssh_key(self):
        fake_key = 'fake key'
        self._test_set_metadata_password(ssh_pub_key=fake_key)

    def test_set_metadata_password_no_ssh_key(self):
        self._test_set_metadata_password(ssh_pub_key=None)

    @mock.patch('cloudbaseinit.plugins.windows.setuserpassword.'
                'SetUserPasswordPlugin._get_password')
    def test_set_password(self, mock_get_password):
        mock_service = mock.MagicMock()
        mock_osutils = mock.MagicMock()
        mock_get_password.return_value = 'fake password'

        response = self._setpassword_plugin._set_password(mock_service,
                                                          mock_osutils,
                                                          'fake user')

        mock_get_password.assert_called_once_with(mock_service, mock_osutils)
        mock_osutils.set_user_password.assert_called_once_with('fake user',
                                                               'fake password')
        self.assertEqual(response, 'fake password')

    @mock.patch('cloudbaseinit.plugins.windows.setuserpassword.'
                'SetUserPasswordPlugin._set_password')
    @mock.patch('cloudbaseinit.plugins.windows.setuserpassword.'
                'SetUserPasswordPlugin._set_metadata_password')
    @mock.patch('cloudbaseinit.osutils.factory.OSUtilsFactory.get_os_utils')
    def test_execute(self, mock_get_os_utils, mock_set_metadata_password,
                     mock_set_password):
        mock_service = mock.MagicMock()
        mock_osutils = mock.MagicMock()
        fake_shared_data = mock.MagicMock()
        fake_shared_data.get.return_value = 'fake username'
        mock_service.is_password_set.return_value = False
        mock_get_os_utils.return_value = mock_osutils
        mock_osutils.user_exists.return_value = True
        mock_set_password.return_value = 'fake password'

        response = self._setpassword_plugin.execute(mock_service,
                                                    fake_shared_data)

        fake_shared_data.get.assert_called_with(
            constants.SHARED_DATA_USERNAME, CONF.username)
        mock_service.is_password_set.assert_called_once_with(
            self._setpassword_plugin._post_password_md_ver)
        mock_get_os_utils.assert_called_once_with()
        mock_osutils.user_exists.assert_called_once_with('fake username')
        mock_set_password.assert_called_once_with(mock_service, mock_osutils,
                                                  'fake username')
        mock_set_metadata_password.assert_called_once_with('fake password',
                                                           mock_service)
        self.assertEqual(response, (2, False))
