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

import threading

import oslo_serialization

from cinder.volume.drivers.emc.coprhd.helpers import commoncoprhdapi as common
from cinder.volume.drivers.emc.coprhd.helpers import consistencygroup
from cinder.volume.drivers.emc.coprhd.helpers import volume


class Snapshot(object):

    # Commonly used URIs for the 'Snapshot' module
    URI_SNAPSHOTS = '/{0}/snapshots/{1}'
    URI_BLOCK_SNAPSHOTS = '/block/snapshots/{0}'
    URI_SEARCH_SNAPSHOT_BY_TAG = '/block/snapshots/search?tag={0}'
    URI_SNAPSHOT_LIST = '/{0}/{1}/{2}/protection/snapshots'
    URI_SNAPSHOT_TASKS_BY_OPID = '/vdc/tasks/{0}'
    URI_RESOURCE_DEACTIVATE = '{0}/deactivate'
    URI_CONSISTENCY_GROUP = "/block/consistency-groups"
    URI_CONSISTENCY_GROUPS_SNAPSHOT_INSTANCE \
        = URI_CONSISTENCY_GROUP + "/{0}/protection/snapshots/{1}"
    URI_CONSISTENCY_GROUPS_SNAPSHOT_DEACTIVATE \
        = URI_CONSISTENCY_GROUPS_SNAPSHOT_INSTANCE + "/deactivate"
    URI_BLOCK_SNAPSHOTS_TAG = URI_BLOCK_SNAPSHOTS + '/tags'

    VOLUMES = 'volumes'
    CG = 'consistency-groups'
    BLOCK = 'block'

    isTimeout = False
    timeout = 300

    def __init__(self, ipAddr, port):
        """Constructor: takes IP address and port of the CoprHD instance

        These are needed to make http requests for REST API
        """
        self.__ipAddr = ipAddr
        self.__port = port

    def snapshot_list_uri(self, otype, otypename, ouri):
        """Makes REST API call to list snapshots under a volume

        Parameters:
            otype     : block
            otypename : either volumes or consistency-groups should be provided
            ouri      : uri of volumes or consistency-group

        Returns:
            return list of snapshots
        """
        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port,
            "GET",
            Snapshot.URI_SNAPSHOT_LIST.format(otype, otypename, ouri), None)
        o = common.json_decode(s)
        return o['snapshot']

    def snapshot_show_uri(self, otype, resourceUri, suri):
        """Retrieves snapshot details based on snapshot Name or Label

        Parameters:
            otype : block
            suri : uri of the Snapshot.
            resourceUri: uri of the source resource
            typename: volumes or consistency-groups should be provided
        Returns:
            Snapshot details in JSON response payload
        """
        if(resourceUri is not None and
           resourceUri.find('BlockConsistencyGroup') > 0):
            (s, h) = common.service_json_request(
                self.__ipAddr, self.__port,
                "GET",
                Snapshot.URI_CONSISTENCY_GROUPS_SNAPSHOT_INSTANCE.format(
                    resourceUri,
                    suri),
                None)
        else:
            (s, h) = common.service_json_request(
                self.__ipAddr, self.__port,
                "GET",
                Snapshot.URI_SNAPSHOTS.format(otype, suri), None)

        return common.json_decode(s)

    def snapshot_query(self, storageresType,
                       storageresTypename, resuri, snapshotName):
        if resuri is not None:
            uris = self.snapshot_list_uri(
                storageresType,
                storageresTypename,
                resuri)
            for uri in uris:
                snapshot = self.snapshot_show_uri(
                    storageresType,
                    resuri,
                    uri['id'])
                if (False == common.get_node_value(snapshot, 'inactive') and
                        snapshot['name'] == snapshotName):
                    return snapshot['id']

        raise common.CoprHdError(
            common.CoprHdError.SOS_FAILURE_ERR,
            _("snapshot with the name: " +
              snapshotName +
              " Not Found"))

    def snapshot_show_task_opid(self, otype, snap, taskid):
        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port,
            "GET",
            Snapshot.URI_SNAPSHOT_TASKS_BY_OPID.format(taskid),
            None)
        if (not s):
            return None
        o = common.json_decode(s)
        return o

    # Blocks the operation until the task is complete/error out/timeout
    def block_until_complete(self, storageresType, resuri,
                             task_id, synctimeout=0):
        if synctimeout:
            t = threading.Timer(synctimeout, common.timeout_handler)
        else:
            t = threading.Timer(self.timeout, common.timeout_handler)
        t.start()
        while True:
            out = self.snapshot_show_task_opid(storageresType, resuri, task_id)

            if out:
                if out["state"] == "ready":
                    # cancel the timer and return
                    t.cancel()
                    break
                # if the status of the task is 'error' then cancel the timer
                # and raise exception
                if out["state"] == "error":
                    # cancel the timer
                    t.cancel()
                    error_message = "Please see logs for more details"
                    if("service_error" in out and
                       "details" in out["service_error"]):
                        error_message = out["service_error"]["details"]
                    raise common.CoprHdError(
                        common.CoprHdError.VALUE_ERR,
                        _("Task: %(task_id)s is failed with error: "
                          "%(error_message)s"),
                        {'task_id': task_id,
                         '.error_message': error_message})

            if self.isTimeout:
                self.isTimeout = False
                raise common.CoprHdError(common.CoprHdError.TIME_OUT,
                                         _("Task did not complete in %d secs."
                                           " Operation timed out. Task in"
                                           " CoprHD will continue"))
        return

    def storage_resource_query(self,
                               storageresType,
                               volumeName,
                               cgName,
                               project,
                               tenant):
        resourcepath = "/" + project + "/"
        if tenant is not None:
            resourcepath = tenant + resourcepath

        resUri = None
        resourceObj = None
        if Snapshot.BLOCK == storageresType and volumeName is not None:
            resourceObj = volume.Volume(self.__ipAddr, self.__port)
            resUri = resourceObj.volume_query(resourcepath + volumeName)
        elif Snapshot.BLOCK == storageresType and cgName is not None:
            resourceObj = consistencygroup.ConsistencyGroup(
                self.__ipAddr,
                self.__port)
            resUri = resourceObj.consistencygroup_query(
                cgName,
                project,
                tenant)
        else:
            resourceObj = None

        return resUri

    def snapshot_create(self, otype, typename, ouri,
                        snaplabel, inactive, sync,
                        readonly=False, synctimeout=0):
        """New snapshot is created, for a given volume

        Parameters:
            otype       : block
                         type should be provided
            typename    : either volume or consistency-groups should
                         be provided
            ouri        : uri of volume
            snaplabel   : name of the snapshot
            inactive    : if true, the snapshot will not activate the
                         synchronization between source and target volumes
            sync        : synchronous request
            synctimeout : Query for task status for "synctimeout" secs.
                          If the task doesn't complete in synctimeout
                          secs, an exception is thrown

        """

        # check snapshot is already exist
        is_snapshot_exist = True
        try:
            self.snapshot_query(otype, typename, ouri, snaplabel)
        except common.CoprHdError as e:
            if e.err_code == common.CoprHdError.NOT_FOUND_ERR:
                is_snapshot_exist = False
            else:
                raise

        if is_snapshot_exist:
            raise common.CoprHdError(
                common.CoprHdError.ENTRY_ALREADY_EXISTS_ERR,
                _("Snapshot with name %(snaplabel)s"
                  " already exists under %(typename)s"),
                {'snaplabel': snaplabel,
                 'typename': typename
                 })

        parms = {
            'name': snaplabel,
            # if true, the snapshot will not activate the synchronization
            # between source and target volumes
            'create_inactive': inactive
        }
        if readonly is True:
            parms['read_only'] = readonly
        body = oslo_serialization.jsonutils.dumps(parms)

        # REST api call
        (s, h) = common.service_json_request(
            self.__ipAddr, self.__port,
            "POST",
            Snapshot.URI_SNAPSHOT_LIST.format(otype, typename, ouri), body)
        o = common.json_decode(s)

        task = o["task"][0]

        if sync:
            return (
                self.block_until_complete(
                    otype,
                    task['resource']['id'],
                    task["id"], synctimeout)
            )
        else:
            return o

    def snapshot_delete_uri(self, otype, resourceUri, suri, sync, synctimeout):
        """Delete a snapshot by uri

        Parameters:
            otype : block
            suri : Uri of the Snapshot
            sync : To perform operation synchronously
            synctimeout : Query for task status for "synctimeout" secs. If
                          the task doesn't complete in synctimeout secs, an
                          exception is thrown
        """
        s = None
        if resourceUri.find("Volume") > 0:

            (s, h) = common.service_json_request(
                self.__ipAddr, self.__port,
                "POST",
                Snapshot.URI_RESOURCE_DEACTIVATE.format(
                    Snapshot.URI_BLOCK_SNAPSHOTS.format(suri)),
                None)
        elif resourceUri.find("BlockConsistencyGroup") > 0:

            (s, h) = common.service_json_request(
                self.__ipAddr, self.__port,
                "POST",
                Snapshot.URI_CONSISTENCY_GROUPS_SNAPSHOT_DEACTIVATE.format(
                    resourceUri,
                    suri),
                None)
        o = common.json_decode(s)
        task = o["task"][0]

        if sync:
            return (
                self.block_until_complete(
                    otype,
                    task['resource']['id'],
                    task["id"], synctimeout)
            )
        else:
            return o

    def snapshot_delete(self, storageresType,
                        storageresTypename, resourceUri,
                        name, sync, synctimeout=0):
        snapshotUri = self.snapshot_query(
            storageresType,
            storageresTypename,
            resourceUri,
            name)
        self.snapshot_delete_uri(
            storageresType,
            resourceUri,
            snapshotUri,
            sync, synctimeout)
