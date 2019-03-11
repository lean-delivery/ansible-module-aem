#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

import requests
from ansible.module_utils.basic import *

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = u'''
---
module: aem_bundle
author:
- Lean Delivery Team
version_added: "1.0"
short_description: Manage AEM Bundles
description:
    - Manage AEM Bundles
options:
    name:
        description:
            - The name of the bundle
        required: true
    action:
        description:
            - start, stop or refresh the Bundle
        required: true
        choices: [start, stop, refresh]
    admin_user:
        description:
            - AEM admin user account name
        required: true
    admin_password:
        description:
            - AEM admin user account password
        required: true
    url:
        description:
            - URL of AEM node
        required: true
'''

EXAMPLES = u'''
# Start AEM bundle
- aem_bundle:
    name: com.day.crx.crxde-support
    action: start
    admin_user: admin
    admin_password: pa$$w0rd
    url: https://aem-node.example.com:4502

# Stop AEM bundle
- aem_bundle:
    name: com.day.crx.crxde-support
    action: stop
    admin_user: admin
    admin_password: pa$$w0rd
    url: https://aem-node.example.com:4502

# Refresh AEM bundle
- aem_bundle:
    name: com.day.crx.crxde-support
    action: refresh
    admin_user: admin
    admin_password: pa$$w0rd
    url: https://aem-node.example.com:4502
'''


class AEMBundle(object):
    """docstring for AEMBundle"""

    def __init__(self, arg):
#        super(AEMBundle, self).__init__()
        self.module = arg
        self.name = self.module.params['name']
        self.action = self.module.params['action']
        self.admin_user = self.module.params['admin_user']
        self.admin_password = self.module.params['admin_password']
        self.url = self.module.params['url']
        self.changed = False
        self.msg = []
        self._get_bnd_status()

    def _get_bnd_status(self):
        aem_request = requests.get('%s/system/console/bundles/%s.json' %
                                   (self.url, self.name),
                                   auth=(self.admin_user,
                                         self.admin_password))
        if aem_request.status_code == 200:
            self.exists = True
            if aem_request.json()['data'][0]['state'] == 'Active':
                self.active = True
            else:
                self.active = False
        else:
            self.exists = False
            self.active = False

    def do_action(self):
        aem_request = requests.post(
            '%s/system/console/bundles/%s' %
            (self.url, self.name), data={
                'action': self.action}, auth=(
                self.admin_user, self.admin_password))
        if aem_request.status_code != 200:
            self.module.fail_json(
                msg='failed to perform %s action on %s bundle - %s' %
                (self.action, aem_request.status_code, aem_request.json()))
        self.changed = True
        self.msg.append(
            'action %s was performmed on bundle %s' %
            (self.action, self.name))

    def show_message(self):
        if self.changed:
            msg = ','.join(self.msg)
            self.module.exit_json(changed=True, msg=msg)
        else:
            self.module.exit_json(changed=False)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(required=True, type='str'),
            action=dict(
                default='start',
                type='str',
                choices=[
                    'start',
                    'stop',
                    'refresh']),
            admin_user=dict(required=True, type='str'),
            admin_password=dict(required=True, type='str', no_log=True),
            url=dict(required=True, type='str')
        ),
        supports_check_mode=False
    )

    bundle = AEMBundle(module)
    bundle.do_action()
    bundle.show_message()


main()
