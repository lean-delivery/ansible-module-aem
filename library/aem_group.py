#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# Copyright: (c) 2016, Paul Markham <https://github.com/pmarkham>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

import requests

DOCUMENTATION = '''
---
module: aem_group
short_description: Manage AEM groups
description:
    - Create, modify, delete and manage permissions AEM groups
author: Paul Markham
contributors: Lean Delivery Team
notes:  
        - This module does group management. 
options:
    id:
        description:
            - The AEM group ID
        required: true
    state:
        description:
            - Create or delete the group
        required: true
        choices: [present, absent]
    name:
        description:
            - Descriptive name of group.
              Only required when creating a new account.
        required: true
    groups:
        description:
            - The of groups the account is in.
              Only required when creating a new account.
        required: true
        default: null
    root_group:
        description:
            - Parent group.
        required: true
        default: null    
    permissions:
        description:
            - Set of permissions for group.
        required: False
        default: null    
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
'''

EXAMPLES = '''
# Create a group
- aem_group: 
    id: sysadmin
    name: 'Systems Administrators'
    groups: 'administrators'
    host: 'http://example.com'
    port: 4502
    admin_user: admin
    admin_password: admin
    permissions:
        - 'path:/,read:true'
        - 'path:/etc/packages,read:true,modify:true,create:true,delete:false,replicate:true'    
    state: present

# Delete a group
- aem_group: 
    id: devs
    host: 'http://example.com'
    port: 4502
    admin_user: admin
    admin_password: admin
    state: absent
'''


# --------------------------------------------------------------------------------
# AEMGroup class.
# --------------------------------------------------------------------------------


class AEMGroup(object):
    def __init__(self, module):
        self.module = module
        self.state = str(self.module.params['state'])
        self.id = str(self.module.params['id'])
        self.name = str(self.module.params['name'])
        self.groups = self.module.params['groups']
        self.admin_user = str(self.module.params['admin_user'])
        self.admin_password = str(self.module.params['admin_password'])
        self.host = str(self.module.params['host'])
        self.port = str(self.module.params['port'])
        self.url = str(self.host + ':' + self.port)
        self.auth = (self.admin_user, self.admin_password)
        self.permissions = self.module.params['permissions']
        self.root_group = self.module.params['root_group']
        self.root_group_path = ''
        self.path = ''
        self.curr_groups = []
        self.curr_name = ''
        self.exists = False

        self.changed = False
        self.msg = []
        self.id_initial = self.id[0]

        if self.module.check_mode:
            self.msg.append('Running in check mode')

        self.aem61 = True
        self.get_group_info()

    # --------------------------------------------------------------------------------
    # Look up group info.
    # --------------------------------------------------------------------------------
    def get_group_info(self):
        if self.aem61:
            r = requests.get(
                self.url + '/bin/querybuilder.json?path=/home/groups&1_property=rep'
                           ':authorizableId&1_property.value=%s&p.limit=-1&p.hits=full' % self.id,
                auth=self.auth
            )
            if r.status_code != 200:
                self.module.fail_json(msg='Error searching for group. status=%s output=%s' % (r.status_code, r.text))
            info = r.json()
            if len(info['hits']) == 0:
                self.exists = False
                return
            self.path = info['hits'][0]['jcr:path']
        else:
            self.path = '/home/groups/%s/%s' % (self.id_initial, self.id)

        r = requests.get(self.url + '%s.rw.json?props=*' % (self.path), auth=self.auth)
        if r.status_code == 200:
            self.exists = True
            info = r.json()
            self.curr_name = info['name']
            self.curr_groups = []
            for entry in info['declaredMemberOf']:
                self.curr_groups.append(entry['authorizableId'])
        else:
            self.exists = False

    # --------------------------------------------------------------------------------
    # Look up root group info.
    # --------------------------------------------------------------------------------
    def get_root_group_path(self):
        if self.aem61:
            r = requests.get(
                self.url + '/bin/querybuilder.json?path=/home/groups&1_property=rep'
                           ':authorizableId&1_property.value=%s&p.limit=-1&p.hits=full' % self.root_group,
                auth=self.auth
            )
            if r.status_code != 200:
                self.module.fail_json(
                    msg='Error searching for root group. status=%s output=%s' % (r.status_code, r.text))
            info = r.json()
            if len(info['hits']) == 0:
                self.exists = False
                return
            self.root_group_path = info['hits'][0]['jcr:path']

    # --------------------------------------------------------------------------------
    # state='present'
    # --------------------------------------------------------------------------------
    def present(self):
        if self.exists:
            # Update existing group
            if self.name:
                if self.curr_name != self.name:
                    self.update_name()
            if self.groups:
                self.curr_groups.sort()
                self.groups.sort()
                curr_groups = ','.join(self.curr_groups).lower()
                groups = ','.join(self.groups).lower()
                if curr_groups != groups:
                    self.update_groups()
            self.add_permissions()
            if self.root_group:
                self.add_to_root_group()
        else:
            # Create new group
            if not self.name:
                self.module.fail_json(msg='Missing required argument: name')
            self.create_group()
            self.add_permissions()
            if self.root_group:
                self.add_to_root_group()

    # --------------------------------------------------------------------------------
    # state='absent'
    # --------------------------------------------------------------------------------
    def absent(self):
        if self.exists:
            self.delete_group()

    # --------------------------------------------------------------------------------
    # Create a new group
    # --------------------------------------------------------------------------------
    def create_group(self):
        fields = [
            ('createGroup', ''),
            ('authorizableId', self.id),
            ('./profile/givenName', self.name),
        ]
        if not self.module.check_mode:
            r = requests.post(self.url + '/libs/granite/security/post/authorizables', auth=self.auth, data=fields)
            self.get_group_info()
            if r.status_code != 201 or not self.exists:
                self.module.fail_json(msg='failed to create group: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("group '%s' created" % self.id)

    # --------------------------------------------------------------------------------
    # Update name
    # --------------------------------------------------------------------------------
    def update_name(self):
        fields = [('profile/givenName', self.name)]
        if not self.module.check_mode:
            r = requests.post(self.url + '%s/.rw.html' % self.path, auth=self.auth, data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to update name: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("name changed from '%s' to '%s'" % (self.curr_name, self.name))

    # --------------------------------------------------------------------------------
    # Update groups
    # --------------------------------------------------------------------------------
    def update_groups(self):
        fields = []
        if not self.module.check_mode:
            for group in self.groups:
                fields.append(('membership', group))
            r = requests.post(self.url + '%s/.rw.html' % self.path, auth=self.auth, data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to update groups: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("groups updated from '%s' to '%s'" % (self.curr_groups, self.groups))

    # --------------------------------------------------------------------------------
    # Add to root group
    # --------------------------------------------------------------------------------
    def add_to_root_group(self):
        if not self.module.check_mode:
            fields = [('addMembers', self.id)]
            r = requests.post(self.url + '%s/.rw.html' % self.root_group_path, auth=self.auth, data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to add to root group: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("group added to '%s'" % self.root_group)

    # --------------------------------------------------------------------------------
    # Delete a group
    # --------------------------------------------------------------------------------
    def delete_group(self):
        fields = [('deleteAuthorizable', '')]
        if not self.module.check_mode:
            r = requests.post(self.url + '%s/.rw.html' % self.path, auth=self.auth, data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to delete group: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("group '%s' deleted" % self.id)

    # --------------------------------------------------------------------------------
    # Add permissions to a group
    # --------------------------------------------------------------------------------
    def add_permissions(self):
        for permission in self.permissions:
            fields = [
                ('authorizableId', self.id),
                ('_charset_', 'utf - 8'),
                ('changelog', permission),
            ]
            if not self.module.check_mode:
                r = requests.post(self.url + '/.cqactions.html', auth=self.auth, data=fields)
                if r.status_code != 200 or not self.exists:
                    self.module.fail_json(msg='failed to add permissions to a group')

    # --------------------------------------------------------------------------------
    # Return status and msg to Ansible.
    # --------------------------------------------------------------------------------
    def exit_status(self):
        msg = ','.join(self.msg)
        self.module.exit_json(changed=self.changed, msg=msg)


# --------------------------------------------------------------------------------
# Mainline.
# --------------------------------------------------------------------------------
def main():
    module = AnsibleModule(
        argument_spec=dict(
            id=dict(required=True),
            state=dict(required=True, choices=['present', 'absent']),
            name=dict(default=None),
            groups=dict(default=None, type='list'),
            admin_user=dict(required=True),
            admin_password=dict(required=True, no_log=True),
            host=dict(required=True),
            port=dict(required=True, type='int'),
            root_group=dict(required=True, type='str'),
            permissions=dict(default=None, type='list'),
        ),
        supports_check_mode=True
    )

    group = AEMGroup(module)

    state = module.params['state']

    if state == 'present':
        group.present()
    elif state == 'absent':
        group.absent()
    else:
        module.fail_json(msg='Invalid state: %s' % state)

    group.exit_status()


# --------------------------------------------------------------------------------
# Ansible boiler plate code.
# --------------------------------------------------------------------------------
from ansible.module_utils.basic import *

main()
