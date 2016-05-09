#!/usr/bin/python

# Copyright (c) 2016 EMC Corporation
# All Rights Reserved
#
# This software contains the intellectual property of EMC Corporation
# or is licensed to EMC Corporation from third parties.  Use of this
# software and the intellectual property contained therein is expressly
# limited to the terms and conditions of the License Agreement under which
# it is provided by or on behalf of EMC.


# import python system modules

from cinder.volume.drivers.emc.coprhd import commoncoprhdapi as common
from cinder.volume.drivers.emc.coprhd.commoncoprhdapi import SOSError
from cinder.volume.drivers.emc.coprhd.project import Project
import json


class ConsistencyGroup(object):
    '''
    The class definition for operations on 'Consistency group Service'.
    '''
    URI_CONSISTENCY_GROUP = "/block/consistency-groups"
    URI_CONSISTENCY_GROUPS_INSTANCE = URI_CONSISTENCY_GROUP + "/{0}"
    URI_CONSISTENCY_GROUPS_DEACTIVATE = URI_CONSISTENCY_GROUPS_INSTANCE + \
        "/deactivate"
    URI_CONSISTENCY_GROUPS_SNAPSHOT = URI_CONSISTENCY_GROUP + \
        "/{0}/protection/snapshots"
    URI_CONSISTENCY_GROUPS_SNAPSHOT_INSTANCE = URI_CONSISTENCY_GROUP + \
        "/{0}/protection/snapshots/{1}"
    URI_CONSISTENCY_GROUPS_SNAPSHOT_ACTIVATE = \
        URI_CONSISTENCY_GROUPS_SNAPSHOT_INSTANCE + "/activate"
    URI_CONSISTENCY_GROUPS_SNAPSHOT_DEACTIVATE = \
        URI_CONSISTENCY_GROUPS_SNAPSHOT_INSTANCE + "/deactivate"
    URI_CONSISTENCY_GROUPS_SNAPSHOT_RESTORE = \
        URI_CONSISTENCY_GROUPS_SNAPSHOT_INSTANCE + "/restore"
    URI_CONSISTENCY_GROUPS_SEARCH = \
        '/block/consistency-groups/search?project={0}'
    URI_SEARCH_CONSISTENCY_GROUPS_BY_TAG = \
        '/block/consistency-groups/search?tag={0}'
    URI_CONSISTENCY_GROUP_TAGS = \
        '/block/consistency-groups/{0}/tags'

    URI_BLOCK_CONSISTENCY_GROUP_PROTECTION_BASE = \
        URI_CONSISTENCY_GROUPS_INSTANCE + "/protection/continuous-copies"
    URI_BLOCK_CONSISTENCY_GROUP_SWAP = \
        URI_BLOCK_CONSISTENCY_GROUP_PROTECTION_BASE + "/swap"
    URI_BLOCK_CONSISTENCY_GROUP_FAILOVER = \
        URI_BLOCK_CONSISTENCY_GROUP_PROTECTION_BASE + "/failover"
    URI_BLOCK_CONSISTENCY_GROUP_FAILOVER_CANCEL = \
        URI_BLOCK_CONSISTENCY_GROUP_PROTECTION_BASE + "/failover-cancel"

    def __init__(self, ipAddr, port):
        '''
        Constructor: takes IP address and port of the ViPR instance. These are
        needed to make http requests for REST API
        '''
        self.__ipAddr = ipAddr
        self.__port = port

    def list(self, project, tenant):
        '''
        This function will give us the list of consistency group uris
        separated by comma.
        parameters:
            project: Name of the project path.
        return
            returns with list of consistency group ids separated by comma.
        '''
        if(tenant is None):
            tenant = ""
        projobj = Project(self.__ipAddr, self.__port)
        fullproj = tenant + "/" + project
        projuri = projobj.project_query(fullproj)

        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port, "GET",
            self.URI_CONSISTENCY_GROUPS_SEARCH.format(projuri), None)
        o = common.json_decode(s)
        if not o:
            return []

        congroups = []
        resources = common.get_node_value(o, "resource")
        for resource in resources:
            congroups.append(resource["id"])

        return congroups

    def show(self, name, project, tenant, xml=False):
        '''
        This function will take consistency group name and project name
        as input and It will display the consistency group with details.
        parameters:
           name : Name of the consistency group.
           project: Name of the project.
        return
            returns with Details of consistency group.
        '''
        uri = self.consistencygroup_query(name, project, tenant)
        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port, "GET",
            self.URI_CONSISTENCY_GROUPS_INSTANCE.format(uri), None)
        o = common.json_decode(s)
        if(o['inactive']):
            return None

        if(xml is False):
            return o

        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port, "GET",
            self.URI_CONSISTENCY_GROUPS_INSTANCE.format(uri), None, None, xml)

        if not s:
            return None
        return s

    def consistencygroup_query(self, name, project, tenant):
        '''
        This function will take consistency group name/id and project name
        as input and returns consistency group id.
        parameters:
           name : Name/id of the consistency group.
        return
            return with id of the consistency group.
         '''
        if (common.is_uri(name)):
            return name

        uris = self.list(project, tenant)
        for uri in uris:
            congroup = self.show(uri, project, tenant)
            if(congroup):
                if (congroup['name'] == name):
                    return congroup['id']
        raise SOSError(SOSError.NOT_FOUND_ERR,
                       "Consistency Group " + name + ": not found")

    # Blocks the opertaion until the task is complete/error out/timeout
    def check_for_sync(self, result, sync, synctimeout=0):
        if(len(result["resource"]) > 0):
            resource = result["resource"]
            return (
                common.block_until_complete("consistencygroup", resource["id"],
                                            result["id"], self.__ipAddr,
                                            self.__port, synctimeout)
            )
        else:
            raise SOSError(
                SOSError.SOS_FAILURE_ERR,
                "error: task list is empty, no task response found")

    def create(self, name, project, tenant):
        '''
        This function will take consistency group name and project name
        as input and it will create the consistency group with the given name.
        parameters:
           name : Name of the consistency group.
           project: Name of the project path.
           tenant: Container tenant name.
        return
            returns with status of creation.
        '''
        # check for existence of consistency group.
        try:
            status = self.show(name, project, tenant)
        except SOSError as e:
            if(e.err_code == SOSError.NOT_FOUND_ERR):
                if(tenant is None):
                    tenant = ""
                fullproj = tenant + "/" + project
                projobj = Project(self.__ipAddr, self.__port)
                projuri = projobj.project_query(fullproj)

                parms = {'name': name, 'project': projuri, }
                body = json.dumps(parms)

                (s, h) = common.service_json_request(
                    self.__ipAddr, self.__port, "POST",
                    self.URI_CONSISTENCY_GROUP, body, None, None)

                o = common.json_decode(s)
                return o
            else:
                raise e
        if(status):
            common.format_err_msg_and_raise(
                "create", "consistency group",
                "consistency group with name: " + name + " already exists",
                SOSError.ENTRY_ALREADY_EXISTS_ERR)

    def delete(self, name, project, tenant, vipronly=False):
        '''
        This function will take consistency group name and project name
        as input and marks the particular consistency group as delete.
        parameters:
           name : Name of the consistency group.
           project: Name of the project.
        return
            return with status of the delete operation.
            false incase it fails to do delete.
        '''
        params = ''
        if (vipronly == True):
            params += "?type=" + 'VIPR_ONLY'
        uri = self.consistencygroup_query(name, project, tenant)
        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port,
            "POST",
            self.URI_CONSISTENCY_GROUPS_DEACTIVATE.format(uri) + params,
            None, None)
        return

    def update(self, name, project, tenant, add_volumes, remove_volumes, sync, synctimeout=0):
        '''
        This function is used to add or remove volumes from consistency group
        It will update the consistency  group with given volumes.
        parameters:
           name : Name of the consistency group.
           project: Name of the project path.
           tenant: Container tenant name.
           add_volumes : volumes to be added to the consistency group
           remove_volumes: volumes to be removed from CG.
        return
            returns with status of creation.
        '''
        if(tenant is None):
            tenant = ""
        fullproj = tenant + "/" + project
        projobj = Project(self.__ipAddr, self.__port)
        projuri = projobj.project_query(fullproj)

        parms = []
        add_voluris = []
        remove_voluris = []
        from cinder.volume.drivers.emc.coprhd.volume import Volume
        volobj = Volume(self.__ipAddr, self.__port)
        if(add_volumes):
            for volname in add_volumes:
                fullvolname = tenant + "/" + project + "/" + volname
                add_voluris.append(volobj.volume_query(fullvolname))
            volumes = {'volume': add_voluris}
            parms = {'add_volumes': volumes}

        if(remove_volumes):
            for volname in remove_volumes:
                fullvolname = tenant + "/" + project + "/" + volname
                remove_voluris.append(volobj.volume_query(fullvolname))
            volumes = {'volume': remove_voluris}
            parms = {'remove_volumes': volumes}

        body = json.dumps(parms)
        uri = self.consistencygroup_query(name, project, tenant)
        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port, "PUT",
            self.URI_CONSISTENCY_GROUPS_INSTANCE.format(uri),
            body, None, None)

        o = common.json_decode(s)
        if(sync):
            return self.check_for_sync(o, sync, synctimeout)
        else:
            return o
