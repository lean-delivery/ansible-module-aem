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
import subprocess


DOCUMENTATION = '''
---
module: aemprimarysync
short_description: wait for primary auth to be in sync with standby
description:
    - Wait for primary author to indicate it's in sync with the standby
author: Paul Markham
options:
    state:
        description:
            - wait for standby sync
        required: true
        choices: [synced]
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
        default: 10
    log:
        description:
            - log file name
        required: false
        default: /opt/adobecq/crx-quickstart/logs/standby.log
    count:
        description:
            - number of matching lines that must occur sequentially to be considered in sync
        required: false
        default: 3
    timeout:
        description:
            - Maximum time, in seconds, to wait for standby to reach sync
        required: false
        default: 3600

'''

EXAMPLES = '''
# Wait for sync
- aemprimarysync: state=synced
          host=auth01
          port=4502
          admin_user=admin
          admin_password=admin
'''
# --------------------------------------------------------------------------------
# AEMUser class.
# --------------------------------------------------------------------------------


class AEMPrimarySync(object):
    def __init__(self, module):
        self.module = module
        self.state = self.module.params['state']
        self.admin_user = self.module.params['admin_user']
        self.admin_password = self.module.params['admin_password']
        self.host = self.module.params['host']
        self.port = self.module.params['port']
        self.log = self.module.params['log']
        self.count = self.module.params['count']
        self.timeout = self.module.params['timeout']

        self.changed = False
        self.msg = []

        if self.module.check_mode:
            self.msg.append('Running in check mode')

    # --------------------------------------------------------------------------------
    # state='synced'
    # --------------------------------------------------------------------------------
    def synced(self):
        if self.module.check_mode:
            self.msg.append('not waiting for sync in check mode')
        else:
            self.watch_log_file()
            self.changed = True
            self.msg.append('synced')

    # --------------------------------------------------------------------------------
    # Watch log file for messages indicating primary and standby have synced
    # --------------------------------------------------------------------------------
    def watch_log_file(self):
        start_time = time.time()
        f = subprocess.Popen(["/usr/bin/tail", "-0f", self.log], stdout=subprocess.PIPE)
        found = 0
        while True:
            line = f.stdout.readline()
            if re.match(".*org.apache.jackrabbit.oak.plugins.segment.standby.store.CommunicationObserver got message 'h' from client.*",
                        line):
                found += 1
                if found >= self.count:
                    self.msg.append('Found %d matching lines' % (found))
                    break
            else:
                found = 0
            now = time.time()
            if now - start_time > self.timeout:
                self.module.fail_json(msg="Waited more than %d seconds -- timed out" % (self.timeout))

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
            port=dict(required=True, type='int'),
            log=dict(default="/opt/adobecq/crx-quickstart/logs/standby.log"),
            count=dict(default=3, type='int'),
            timeout=dict(default=3600, type='int'),
        ),
        supports_check_mode=True
    )

    sync = AEMPrimarySync(module)

    state = module.params['state']

    if state == 'synced':
        sync.synced()
    else:
        module.fail_json(msg='Invalid state: %s' % state)

    sync.exit_msg()


# --------------------------------------------------------------------------------
# Ansible boiler plate code.
# --------------------------------------------------------------------------------
main()
