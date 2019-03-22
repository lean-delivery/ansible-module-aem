#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# Copyright: (c) 2016, Paul Markham <https://github.com/pmarkham>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.basic import *
import sys
import os
import platform
import httplib
import urllib
import base64
import json
import string
import random
import re


DOCUMENTATION = '''
---
module: aemstanbysync
short_description: Manage auth standby sync
description:
    - Manage standby sync service
author: Paul Markham
options:
    state:
        description:
            - Stop, start or wait for standby sync
        required: true
        choices: [started, stopped, synced]
    admin_user:
        description:
            - AEM admin user account name
        required: true
    admin_password:
        description:
            - AEM admin user account password
        required: true
    host:
        description:
            - Host name where AEM is running
        required: true
    port:
        description:
            - Port number that AEM is listening on
        required: true
    lag:
        description:
            - Time, in seconds, under which the standby is considering in sync. This is needed as the sync time is always
              changing, but under normal circumstances should be under 10 seconds.
        required: false
        default: 10
    timeout:
        description:
            - Maximum time, in seconds, to wait for standby to reach sync
        required: false
        default: 3600
    wait:
        description:
            - wait time before checking or changing state. This is to give AEM a chance to finish initialising JMX
              after it's been started as sometimes it's not quite ready.
        required: false
        default: 0

'''

EXAMPLES = '''
# Stop sync service
- aemstandbysync: state=stopped
                  host=auth01
                  port=4502
                  admin_user=admin
                  admin_password=admin

# Start syn service
- aemstandbysync: state=started
                  host=auth01
                  port=4502
                  admin_user=admin
                  admin_password=admin

# Wait for sync (Second Since Last Success)
- aemstandbysync: state=synced
                  host=auth01
                  port=4502
                  admin_user=admin
                  admin_password=admin
'''
# --------------------------------------------------------------------------------
# AEMStandbySync class.
# --------------------------------------------------------------------------------


class AEMStandBySync(object):
    def __init__(self, module):
        self.module = module
        self.state = self.module.params['state']
        self.admin_user = self.module.params['admin_user']
        self.admin_password = self.module.params['admin_password']
        self.host = self.module.params['host']
        self.port = self.module.params['port']
        self.lag = self.module.params['lag']
        self.timeout = self.module.params['timeout']

        self.changed = False
        self.msg = []

        if self.module.check_mode:
            self.msg.append('Running in check mode')

        self.sync_secs = 0
        self.get_sync_state()

    # --------------------------------------------------------------------------------
    # Look up sync info.
    # --------------------------------------------------------------------------------

    def get_sync_state(self):
        start_time = time.time()
        while True:
            now = time.time()
            if now - start_time > self.timeout:
                self.module.fail_json(msg="Waited more than %d seconds to get JMX configuration -- timed out" % (self.timeout))
            (status, output) = self.http_request('GET', '/system/console/jmx')
            if status == 200:
                break
            else:
                time.sleep(10)

        matches = 0
        for line in output.split('\n'):
            if re.match('.*Standby.*', line):
                matches = matches + 1
                standby_line = line
        if matches != 1:
            self.module.fail_json(msg="Expected 1 standby line in JMX output, got %d" % matches)

        m = re.match("^.*href='(.*)'>.*", standby_line)
        if m:
            self.url = m.group(1)
        else:
            self.module.fail_json(msg="Couldn't find standby url in line '%s'" % (standby_line))

        (status, output) = self.http_request('GET', self.url)
        if status != 200:
            self.module.fail_json(msg="Error getting standby configuration. status=%s output=%s" % (status, output))
        self.sync_state = ''
        self.sync_secs = None
        self.failed_requests = None
        for line in output.split('\n'):
            m = re.match("^.*'>FailedRequests<.*<td data-type='int'>(.*)</td>.*", line)
            if m:
                self.failed_requests = int(m.group(1))
            m = re.match("^.*'>SecondsSinceLastSuccess<.*<td data-type='int'>(.*)</td>.*", line)
            if m:
                self.sync_secs = int(m.group(1))
            m = re.match("^.*'>Status<.*<td data-type='java.lang.String'>(.*)</td>.*", line)
            if m:
                self.sync_state = m.group(1)
        if self.failed_requests is None:
            self.module.fail_json(msg="Couldn't determine failed requests: Got '%d'" % (self.failed_requests))
        if self.sync_secs is None:
            self.module.fail_json(msg="Couldn't determine seconds since last sync: Got '%d'" % (self.sync_secs))
        if self.sync_state not in ['running', 'stopped', 'initializing']:
            self.module.fail_json(msg="Couldn't determine sync state: Got '%s'" % (self.sync_state))

    # --------------------------------------------------------------------------------
    # state='started'
    # --------------------------------------------------------------------------------

    def started(self):
        if self.sync_state == 'running':
            self.msg.append('sync already started')
        else:
            if not self.module.check_mode:
                (status, output) = self.http_request('POST', self.url + '/op/start/')
                if status != 200:
                    self.module.fail_json(msg="Error starting sync. status=%s output=%s" % (status, output))
                self.get_sync_state()
                if self.sync_state != 'running':
                    self.module.fail_json(msg="Failed to start sync")
            self.msg.append('sync started')
            self.changed = True

    # --------------------------------------------------------------------------------
    # state='stopped'
    # --------------------------------------------------------------------------------

    def stopped(self):
        if self.sync_state == 'stopped':
            self.msg.append('sync already stopped')
        else:
            if not self.module.check_mode:
                (status, output) = self.http_request('POST', self.url + '/op/stop/')
                if status != 200:
                    self.module.fail_json(msg="Error starting sync. status=%s output=%s" % (status, output))
                self.get_sync_state()
                if self.sync_state != 'stopped':
                    self.module.fail_json(msg="Failed to stop sync")
            self.msg.append('sync stopped')
            self.changed = True

    # --------------------------------------------------------------------------------
    # state='synced'
    # --------------------------------------------------------------------------------
    def synced(self):
        if self.module.check_mode:
            self.msg.append('not waiting for sync in check mode')
        else:
            if self.sync_state != 'running':
                self.module.fail_json(msg="State is not 'running'. Can't wait for sync.")
            start_time = time.time()
            while self.failed_requests > 0 or self.sync_secs > self.lag:
                now = time.time()
                if now - start_time > self.timeout:
                    self.module.fail_json(msg="Waited more than %d seconds -- timed out" % (self.timeout))
                self.changed = True
                time.sleep(10)
                self.get_sync_state()
            self.msg.append('standby synced')

    # --------------------------------------------------------------------------------
    # Issue http request.
    # --------------------------------------------------------------------------------
    def http_request(self, method, url, fields=None):
        headers = {'Authorization': 'Basic ' + base64.b64encode(self.admin_user + ':' + self.admin_password)}
        if fields:
            data = urllib.urlencode(fields)
            headers['Content-type'] = 'application/x-www-form-urlencoded'
        else:
            data = None
        conn = httplib.HTTPConnection(self.host + ':' + self.port)
        try:
            conn.request(method, url, data, headers)
        except Exception as e:
            self.module.fail_json(msg="http request '%s %s' failed: %s" % (method, url, e))
        resp = conn.getresponse()
        output = resp.read()
        return (resp.status, output)

    # --------------------------------------------------------------------------------
    # Return status and msg to Ansible.
    # --------------------------------------------------------------------------------

    def exit_msg(self):
        msg = ','.join(self.msg)
        self.module.exit_json(changed=self.changed, msg=msg)


# --------------------------------------------------------------------------------
# Mainline.
# --------------------------------------------------------------------------------
def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(required=True, choices=['started', 'stopped', 'synced']),
            admin_user=dict(required=True),
            admin_password=dict(required=True, no_log=True),
            host=dict(required=True),
            port=dict(required=True),
            lag=dict(default=10, type='int'),
            timeout=dict(default=3600, type='int'),
            wait=dict(default=0, type='int'),
        ),
        supports_check_mode=True
    )

    time.sleep(int(module.params['wait']))

    sync = AEMStandBySync(module)

    state = module.params['state']

    if state == 'started':
        sync.started()
    elif state == 'stopped':
        sync.stopped()
    elif state == 'synced':
        sync.synced()
    else:
        module.fail_json(msg='Invalid state: %s' % state)

    sync.exit_msg()


# --------------------------------------------------------------------------------
# Ansible boiler plate code.
# --------------------------------------------------------------------------------
main()
