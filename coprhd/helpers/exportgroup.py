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

import oslo_serialization

from cinder.i18n import _
from cinder.volume.drivers.emc.coprhd.helpers import commoncoprhdapi as common
from cinder.volume.drivers.emc.coprhd.helpers import host
from cinder.volume.drivers.emc.coprhd.helpers import project
from cinder.volume.drivers.emc.coprhd.helpers import virtualarray
from cinder.volume.drivers.emc.coprhd.helpers import volume


class ExportGroup(object):

    URI_EXPORT_GROUP = "/block/exports"
    URI_EXPORT_GROUPS_SHOW = URI_EXPORT_GROUP + "/{0}"
    URI_EXPORT_GROUP_SEARCH = '/block/exports/search'
    URI_EXPORT_GROUP_UPDATE = '/block/exports/{0}'

    def __init__(self, ipAddr, port):
        """Constructor: takes IP address and port of the CoprHD instance

        These are needed to make http requests for REST API
        """
        self.__ipAddr = ipAddr
        self.__port = port

    def exportgroup_remove_volumes_by_uri(self, exportgroup_uri, volumeIdList,
                                          sync=False, tenantname=None,
                                          projectname=None,
                                          cg=None, synctimeout=0):
        """Remove volumes from the exportgroup, given the uris of volume"""

        volume_list = volumeIdList
        parms = {}

        parms['volume_changes'] = self._remove_list(volume_list)
        o = self.send_json_request(exportgroup_uri, parms)
        return self.check_for_sync(o, sync, synctimeout)

    def _remove_list(self, uris):
        resChanges = {}
        if not isinstance(uris, list):
            resChanges['remove'] = [uris]
        else:
            resChanges['remove'] = uris
        return resChanges

    def send_json_request(self, exportgroup_uri, param):
        body = oslo_serialization.jsonutils.dumps(param)
        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port, "PUT",
            self.URI_EXPORT_GROUP_UPDATE.format(exportgroup_uri), body)
        return common.json_decode(s)

    def check_for_sync(self, result, sync, synctimeout=0):
        if sync:
            if len(result["resource"]) > 0:
                resource = result["resource"]
                return (
                    common.block_until_complete("export", resource["id"],
                                                result["id"], self.__ipAddr,
                                                self.__port, synctimeout)
                )
            else:
                raise common.CoprHdError(
                    common.CoprHdError.SOS_FAILURE_ERR, _(
                        "error: task list is empty, no task response found"))
        else:
            return result

    def exportgroup_list(self, project_name, tenant):
        """This function gives us list of export group uris separated by comma

        Parameters:
            project_name: Name of the project path
        return
            returns with list of export group ids separated by comma
        """
        if tenant is None:
            tenant = ""
        projobj = project.Project(self.__ipAddr, self.__port)
        fullproj = tenant + "/" + project_name
        projuri = projobj.project_query(fullproj)

        uri = self.URI_EXPORT_GROUP_SEARCH

        if '?' in uri:
            uri += '&project=' + projuri
        else:
            uri += '?project=' + projuri

        (s, h) = common.service_json_request(self.__ipAddr, self.__port, "GET",
                                             uri, None)
        o = common.json_decode(s)
        if not o:
            return []

        exportgroups = []
        resources = common.get_node_value(o, "resource")
        for resource in resources:
            exportgroups.append(resource["id"])

        return exportgroups

    def exportgroup_show(self, name, project, tenant, varray=None):
        """This function display the Export group with details

        Parameters:
           name : Name of the export group
           project: Name of the project
        return
            returns with Details of export group
        """
        varrayuri = None
        if varray:
            varrayObject = virtualarray.VirtualArray(
                self.__ipAddr, self.__port)
            varrayuri = varrayObject.varray_query(varray)
        uri = self.exportgroup_query(name, project, tenant, varrayuri)
        (s, h) = common.service_json_request(
            self.__ipAddr,
            self.__port,
            "GET",
            self.URI_EXPORT_GROUPS_SHOW.format(uri), None)
        o = common.json_decode(s)
        if o['inactive']:
            return None

        return o

    def exportgroup_create(self, name, project, tenant, varray,
                           exportgrouptype, export_destination=None):
        """This function creates the Export group with given name

        Parameters:
           name : Name of the export group
           project: Name of the project path
           tenant: Container tenant name
        return
            returns with status of creation
        """
        # check for existence of export group.
        try:
            status = self.exportgroup_show(name, project, tenant)
        except common.CoprHdError as e:
            if e.err_code == common.CoprHdError.NOT_FOUND_ERR:
                if tenant is None:
                    tenant = ""

                fullproj = tenant + "/" + project
                projObject = project.Project(self.__ipAddr, self.__port)
                projuri = projObject.project_query(fullproj)

                varrayObject = virtualarray.VirtualArray(
                    self.__ipAddr, self.__port)
                nhuri = varrayObject.varray_query(varray)

                parms = {
                    'name': name,
                    'project': projuri,
                    'varray': nhuri,
                    'type': exportgrouptype
                }

                if exportgrouptype and export_destination:
                    host_obj = host.Host(self.__ipAddr, self.__port)
                    try:
                        host_uri = host_obj.query_by_name(
                            export_destination)
                    except common.CoprHdError as ex:
                        raise ex
                    parms['hosts'] = [host_uri]

                body = oslo_serialization.jsonutils.dumps(parms)
                (s, h) = common.service_json_request(self.__ipAddr,
                                                     self.__port, "POST",
                                                     self.URI_EXPORT_GROUP,
                                                     body)

                o = common.json_decode(s)
                return o
            else:
                raise

        if status:
            raise common.CoprHdError(
                common.CoprHdError.ENTRY_ALREADY_EXISTS_ERR, (_(
                    "Export group with name %s"
                    " already exists"), name))

    def exportgroup_query(self, name, project, tenant, varrayuri=None):
        """Makes REST API call to query the exportgroup by name

        Parameters:
            name : Name/id of the export group.
        return
            return with id of the export group.
        """
        if common.is_uri(name):
            return name

        uris = self.exportgroup_list(project, tenant)
        for uri in uris:
            exportgroup = self.exportgroup_show(uri, project, tenant)
            if exportgroup and exportgroup['name'] == name:
                if varrayuri:
                    varrayobj = exportgroup['varray']
                    if varrayobj['id'] == varrayuri:
                        return exportgroup['id']
                    else:
                        continue
                else:
                    return exportgroup['id']
        raise common.CoprHdError(
            common.CoprHdError.NOT_FOUND_ERR,
            (_("Export Group %s: not found"), name))

    def exportgroup_add_volumes(self, sync, exportgroupname, tenantname,
                                maxpaths, minpaths, pathsperinitiator,
                                projectname, volumenames,
                                cg=None, synctimeout=0, varray=None):
        """Add volume to export group

        Parameters:
           sync              : synchronous request
           exportgroupname   : Name/id of the export group.
           tenantname        : tenant name
           maxpaths          : Maximum number of paths
           minpaths          : Minimum number of paths
           pathsperinitiator : Paths per initiator
           projectname       : name of project
           volumenames       : names of volumes that needs
                               to be added to exportgroup
           cg                : consistency group
           synctimeout       : Query for task status for "synctimeout" secs.
                               If the task doesn't complete in synctimeout
                               secs, an exception is thrown
           varray            : Name of varray

        return
            return action result
        """
        varrayuri = None
        if varray:
            varrayObject = virtualarray.VirtualArray(
                self.__ipAddr, self.__port)
            varrayuri = varrayObject.varray_query(varray)

        exportgroup_uri = self.exportgroup_query(exportgroupname,
                                                 projectname,
                                                 tenantname,
                                                 varrayuri)

        # get volume uri
        if tenantname is None:
            tenantname = ""
        # List of volumes
        volume_list = []

        if volumenames:
            volume_list = self._get_resource_lun_tuple(
                volumenames, "volumes", None, tenantname,
                projectname, None)

        parms = {}
        # construct the body

        volChanges = {}
        volChanges['add'] = volume_list
        path_parameters = {}

        if maxpaths:
            path_parameters['max_paths'] = maxpaths
        if minpaths:
            path_parameters['min_paths'] = minpaths
        if pathsperinitiator is not None:
            path_parameters['paths_per_initiator'] = pathsperinitiator

        parms['path_parameters'] = path_parameters
        parms['volume_changes'] = volChanges

        o = self.send_json_request(exportgroup_uri, parms)
        return self.check_for_sync(o, sync, synctimeout)

    def _get_resource_lun_tuple(self, resources, resType, baseResUri,
                                tenantname, projectname, blockTypeName):
        """Function to validate input volumes and return list of ids and luns

        input
            list of volumes in the format name:lun
        """

        copyEntries = []
        volumeObject = volume.Volume(self.__ipAddr, self.__port)
        for copy in resources:
            copyParam = []
            try:
                copyParam = copy.split(":")
            except Exception:
                raise common.CoprHdError(
                    common.CoprHdError.CMD_LINE_ERR,
                    (_("Please provide valid format volume:"
                       " lun for parameter %s"),
                     resType))
            copy = dict()
            if not len(copyParam):
                raise common.CoprHdError(
                    common.CoprHdError.CMD_LINE_ERR,
                    (_("Please provide at least volume for parameter %s"),
                     resType))
            if resType == "volumes":
                fullvolname = tenantname + "/" + projectname + "/"
                fullvolname += copyParam[0]
                copy['id'] = volumeObject.volume_query(fullvolname)
            if len(copyParam) > 1:
                copy['lun'] = copyParam[1]
            copyEntries.append(copy)
        return copyEntries
