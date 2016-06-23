# Copyright (c) 2016 EMC Corporation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


"""Driver for EMC CoprHD ScaleIO volumes"""

import requests
from six.moves import urllib

from oslo_log import log as logging

from cinder import exception
from cinder.i18n import _
from cinder.i18n import _LI
from cinder import interface
from cinder.volume import driver
from cinder.volume.drivers.coprhd import common as CoprHD_common


LOG = logging.getLogger(__name__)


@interface.volumedriver
class EMCCoprHDScaleIODriver(driver.VolumeDriver):
    """CoprHD ScaleIO Driver"""
    server_token = None

    def __init__(self, *args, **kwargs):
        super(EMCCoprHDScaleIODriver, self).__init__(*args, **kwargs)
        self.common = self._get_common_driver()

    def _get_common_driver(self):
        return CoprHD_common.EMCCoprHDDriverCommon(
            protocol='scaleio',
            default_backend_name=self.__class__.__name__,
            configuration=self.configuration)

    def check_for_setup_error(self):
        self.common.check_for_setup_error()

    def create_volume(self, volume):
        """Creates a Volume."""
        self.common.create_volume(volume, self, "scaleio")
        self.common.set_volume_tags(volume, ['_obj_volume_type'], "scaleio")
        volSize = self.updateVolumeSize(int(volume['size']))
        return {'size': volSize}

    def updateVolumeSize(self, volSize):
        """update the openstack volume size"""
        defaultSize = 8
        if((volSize % defaultSize) != 0):
            return (volSize / defaultSize) * defaultSize + defaultSize
        else:
            return volSize

    def create_cloned_volume(self, volume, src_vref):
        """Creates a cloned Volume."""
        self.common.create_cloned_volume(volume, src_vref)
        self.common.set_volume_tags(volume, ['_obj_volume_type'])

    def create_volume_from_snapshot(self, volume, snapshot):
        """Creates a volume from a snapshot."""
        self.common.create_volume_from_snapshot(snapshot, volume)
        self.common.set_volume_tags(volume, ['_obj_volume_type'])

    def extend_volume(self, volume, new_size):
        """expands the size of the volume."""
        self.common.expand_volume(volume, new_size)

    def delete_volume(self, volume):
        """Deletes an volume."""
        self.common.delete_volume(volume)

    def create_snapshot(self, snapshot):
        """Creates a snapshot."""
        self.common.create_snapshot(snapshot)

    def delete_snapshot(self, snapshot):
        """Deletes a snapshot."""
        self.common.delete_snapshot(snapshot)

    def ensure_export(self, context, volume):
        """Driver entry point to get the export info for an existing volume"""
        pass

    def create_export(self, context, volume, connector=None):
        """Driver entry point to get the export info for a new volume."""
        pass

    def remove_export(self, context, volume):
        """Driver exntry point to remove an export for a volume"""
        pass

    def create_consistencygroup(self, context, group):
        """Creates a consistencygroup."""
        return self.common.create_consistencygroup(context, group)

    def update_consistencygroup(self, context, group,
                                add_volumes, remove_volumes):
        """Updates volumes in consistency group."""
        return self.common.update_consistencygroup(self, context, group,
                                                   add_volumes, remove_volumes)

    def delete_consistencygroup(self, context, group):
        """Deletes a consistency group."""
        return self.common.delete_consistencygroup(self, context, group)

    def create_cgsnapshot(self, context, cgsnapshot, snapshots):
        """Creates a cgsnapshot."""
        return self.common.create_cgsnapshot(self, context,
                                             cgsnapshot, snapshots)

    def delete_cgsnapshot(self, context, cgsnapshot, snapshots):
        """Deletes a cgsnapshot."""
        return self.common.delete_cgsnapshot(self, context,
                                             cgsnapshot, snapshots)

    def check_for_export(self, context, volume_id):
        """Make sure volume is exported."""
        pass

    def initialize_connection(self, volume, connector):
        """Initializes the connection and returns connection info.

        the scaleio driver returns a driver_volume_type of 'scaleio'.
        the format of the driver data is defined as:
            :scaleIO_volname:    name of the volume
            :hostIP:    The IP address of the openstack host to which we
                want to export the scaleio volume.
            :serverIP:     The IP address of the REST gateway of the ScaleIO.
            :serverPort:   The port of the REST gateway of the ScaleIO.
            :serverUsername: The username to access REST gateway of ScaleIO.
            :serverPassword:    The password to access REST gateway of ScaleIO.
            :iopsLimit:    iops limit.
            :bandwidthLimit:    bandwidth Limit.

        Example return value::

            {
                'driver_volume_type': 'scaleio'
                'data': {
                    'scaleIO_volname': vol_1,
                    'hostIP': '10.63.20.12',
                    'serverIP': '10.63.20.176',
                    'serverPort': '443'
                    'serverUsername': 'admin'
                    'serverPassword': 'password'
                    'iopsLimit': None
                    'bandwidthLimit': None
                }
            }

        """

        volname = self.common._get_volume_name(volume)

        properties = {}
        properties['scaleIO_volname'] = volname
        properties['hostIP'] = connector['ip']
        properties[
            'serverIP'] = self.configuration.coprhd_scaleio_rest_gateway_ip
        properties[
            'serverPort'] = self.configuration.coprhd_scaleio_rest_gateway_port
        properties[
            'serverUsername'] = (
            self.configuration.coprhd_scaleio_rest_server_username)
        properties[
            'serverPassword'] = (
            self.configuration.coprhd_scaleio_rest_server_password)
        properties['iopsLimit'] = None
        properties['bandwidthLimit'] = None
        properties['serverToken'] = self.server_token

        initiatorPorts = []
        initiatorPort = self._get_client_id(properties['serverIP'],
                                            properties['serverPort'],
                                            properties['serverUsername'],
                                            properties['serverPassword'],
                                            properties['hostIP'])
        initiatorPorts.append(initiatorPort)

        properties['serverToken'] = self.server_token
        protocol = 'scaleio'
        hostname = connector['host']
        self.common.initialize_connection(volume,
                                          protocol,
                                          initiatorPorts,
                                          hostname)

        dictobj = {
            'driver_volume_type': 'scaleio',
            'data': properties
        }

        return dictobj

    def terminate_connection(self, volume, connector, **kwargs):
        """Disallow connection from connector"""

        volname = volume['display_name']
        properties = {}
        properties['scaleIO_volname'] = volname
        properties['hostIP'] = connector['ip']
        properties[
            'serverIP'] = self.configuration.coprhd_scaleio_rest_gateway_ip
        properties[
            'serverPort'] = self.configuration.coprhd_scaleio_rest_gateway_port
        properties[
            'serverUsername'] = (
            self.configuration.coprhd_scaleio_rest_server_username)
        properties[
            'serverPassword'] = (
            self.configuration.coprhd_scaleio_rest_server_password)
        properties['serverToken'] = self.server_token

        initiatorPort = self._get_client_id(properties['serverIP'],
                                            properties['serverPort'],
                                            properties['serverUsername'],
                                            properties['serverPassword'],
                                            properties['hostIP'])
        protocol = 'scaleio'
        hostname = connector['host']
        initPorts = []
        initPorts.append(initiatorPort)
        self.common.terminate_connection(volume,
                                         protocol,
                                         initPorts,
                                         hostname)

    def get_volume_stats(self, refresh=False):
        """Get volume status.

        If 'refresh' is True, run update the stats first.
        """
        if refresh:
            self.update_volume_stats()

        return self._stats

    def update_volume_stats(self):
        """Retrieve stats info from virtual pool/virtual array."""
        LOG.debug("Updating volume stats")
        self._stats = self.common.update_volume_stats()

    def _get_client_id(self, server_ip, server_port, server_username,
                       server_password, sdc_ip):
        ip_encoded = urllib.parse.quote(sdc_ip, '')
        ip_double_encoded = urllib.parse.quote(ip_encoded, '')
        request = ("https://" + server_ip + ":" + server_port +
                   "/api/types/Sdc/instances/getByIp::" +
                   ip_double_encoded + "/")
        LOG.info(_LI("ScaleIO get client id by ip request: %s"), request)

        if self.configuration.scaleio_verify_server_certificate:
            verify_cert = self.configuration.scaleio_server_certificate_path
        else:
            verify_cert = False

        r = None

        r = requests.get(
            request, auth=(server_username, self.server_token),
            verify=verify_cert)
        r = self._check_response(
            r, request, server_ip, server_port,
            server_username, server_password)

        sdc_id = r.json()
        if (sdc_id == '' or sdc_id is None):
            msg = (_("Client with ip %s wasn't found "), sdc_ip)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        if (r.status_code != 200 and "errorCode" in sdc_id):
            msg = (_("Error getting sdc id from ip %(sdc_ip)s:"
                     " %(sdc_id_message)s"), {'sdc_ip': sdc_ip,
                                              'sdc_id_message': sdc_id[
                                                  'message']})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        LOG.info(_LI("ScaleIO sdc id is %s"), sdc_id)
        return sdc_id

    def _check_response(self, response, request,
                        server_ip, server_port,
                        server_username, server_password):
        if (response.status_code == 401 or response.status_code == 403):
            LOG.info(
                _LI("Token is invalid, going to re-login and get a new one"))
            login_request = ("https://" + server_ip +
                             ":" + server_port + "/api/login")
            if self.configuration.scaleio_verify_server_certificate:
                verify_cert = (
                    self.configuration.scaleio_server_certificate_path)
            else:
                verify_cert = False

            r = requests.get(
                login_request, auth=(server_username, server_password),
                verify=verify_cert)

            token = r.json()
            self.server_token = token
            # repeat request with valid token
            LOG.info(_LI("going to perform request again %s with valid token"),
                     request)
            res = requests.get(
                request, auth=(server_username, self.server_token),
                verify=verify_cert)
            return res
        return response

    def retype(self, ctxt, volume, new_type, diff, host):
        """Change the volume type"""
        return self.common.retype(ctxt, volume, new_type, diff, host)
