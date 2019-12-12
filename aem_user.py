#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# Copyright: (c) 2016, Paul Markham <https://github.com/pmarkham>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.basic import *
import json
import requests
import random
import re

DOCUMENTATION = '''
---
module: aem_user
short_description: Manage AEM users
description:
    - Create, modify and delete AEM users
author: Paul Markham, Lean Delivery Team
notes:
    - The password specified is the initial password and is only used when the account is created.
      If the account exists, the password isn't changed.
options:
    id:
        description:
            - The AEM user name
        required: true
    state:
        description:
            - Create or delete the account
        required: true
        choices: [present, absent]
    first_name:
        description:
            - First name of user.
              Only required when creating a new account.
        required: true
    last_name:
        description:
            - Last name of user.
              Only required when creating a new account.
        required: true
    password:
        description:
            - Initial password when account is created. Not used if account already exists.
              Only required when creating a new account.
        required: true
    groups:
        description:
            - The of groups the account is in.
              Only required when creating a new account.
        required: true
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
# Create a user
- aem_user:
    id: bbaggins
    first_name: Bilbo
    last_name: Baggins
    password: myprecious
    groups: 'immortality,invisibility'
    host: auth01
    port: 4502
    admin_user: admin
    admin_password: admin
    state: present

# Delete a user
- aem_user:
    id: golum
    port: 4502
    admin_user: admin
    admin_password: admin
    state: absent
'''


# --------------------------------------------------------------------------------
# AEMUser class.
# --------------------------------------------------------------------------------
class AEMUser(object):
    def __init__(self, module):
        self.module = module
        self.state = self.module.params['state']
        self.id = self.module.params['id']
        self.first_name = self.module.params['first_name']
        self.last_name = self.module.params['last_name']
        self.groups = self.module.params['groups']
        self.password = self.module.params['password']
        self.admin_user = self.module.params['admin_user']
        self.admin_password = self.module.params['admin_password']
        self.host = str(self.module.params['host'])
        self.port = str(self.module.params['port'])
        self.url = self.host + ':' + self.port
        self.auth = (self.admin_user, self.admin_password)

        self.changed = False
        self.msg = []
        self.id_initial = self.id[0]

        if self.module.check_mode:
            self.msg.append('Running in check mode')

        self.aem61 = True
        if "everyone" not in self.groups:
            # everyone group not listed, so add it
            self.groups.append("everyone")

        self.get_user_info()

    # --------------------------------------------------------------------------------
    # Look up user info.
    # --------------------------------------------------------------------------------
    def get_user_info(self):
        if self.aem61:
            r = requests.get(self.url + '/bin/querybuilder.json?path=/home/users&1_'
                                        'property=rep:authorizableId&1_property.value=%s&p.limit=-1&p.hits=full' % self.id,
                             auth=self.auth)
            if r.status_code != 200:
                self.module.fail_json(msg="Error searching for user '%s'. status=%s output=%s"
                                          % (self.id, r.status_code, r.text))
            info = json.loads(r.text)
            if len(info['hits']) == 0:
                self.exists = False
                return
            self.path = info['hits'][0]['jcr:path']
        else:
            self.path = '/home/users/%s/%s' % (self.id_initial, self.id)

        r = requests.get(self.url + '%s.rw.json?props=*' % self.path, auth=self.auth)
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
    # state='present'
    # --------------------------------------------------------------------------------
    def present(self):
        if self.exists:
            # Update existing user
            if self.first_name and self.last_name:
                full_name = '%s %s' % (self.first_name, self.last_name)
                if self.curr_name != full_name:
                    self.update_name()
            elif self.first_name and not self.last_name:
                self.module.fail_json(msg='Missing required argumanet: last_name')
            elif self.last_name and not self.first_name:
                self.module.fail_json(msg='Missing required argumanet: first_name')

            if self.groups:
                self.curr_groups.sort()
                self.groups.sort()
                curr_groups = ','.join(self.curr_groups)
                groups = ','.join(self.groups)
                if curr_groups != groups:
                    self.update_groups()
        else:
            # Create a new user
            if self.password:
                self.check_password()
            else:
                self.generate_password()
            if not self.first_name:
                self.module.fail_json(msg='Missing required argument: first_name')
            if not self.last_name:
                self.module.fail_json(msg='Missing required argument: last_name')
            if not self.groups:
                self.module.fail_json(msg='Missing required argument: groups')
            self.create_user()

    # --------------------------------------------------------------------------------
    # state='absent'
    # --------------------------------------------------------------------------------
    def absent(self):
        if self.exists:
            self.delete_user()

    # --------------------------------------------------------------------------------
    # Create a new user
    # --------------------------------------------------------------------------------
    def create_user(self):
        fields = [
            ('createUser', ''),
            ('authorizableId', self.id),
            ('profile/givenName', self.first_name),
            ('profile/familyName', self.last_name),
        ]
        if not self.module.check_mode:
            if self.password:
                fields.append(('rep:password', self.password))
            for group in self.groups:
                fields.append(('membership', group))
            r = requests.post(self.url + '/libs/granite/security/post/authorizables', fields, auth=self.auth)
            self.get_user_info()
            if r.status_code != 201 or not self.exists:
                self.module.fail_json(msg='failed to create user: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("user '%s' created" % (self.id))

    # --------------------------------------------------------------------------------
    # Update name
    # --------------------------------------------------------------------------------
    def update_name(self):
        fields = [
            ('profile/givenName', self.first_name),
            ('profile/familyName', self.last_name),
        ]
        if not self.module.check_mode:
            r = requests.post(self.url + '%s.rw.html' % self.path, fields, auth=self.auth)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to update name: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("name updated from '%s' to '%s %s'" % (self.curr_name, self.first_name, self.last_name))

    # --------------------------------------------------------------------------------
    # Update groups
    # --------------------------------------------------------------------------------
    def update_groups(self):
        fields = []
        for group in self.groups:
            fields.append(('membership', group))
        if not self.module.check_mode:
            r = requests.post(self.url + '%s.rw.html' % self.path, fields, auth=self.auth)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to update groups: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("groups updated from '%s' to '%s'" % (self.curr_groups, self.groups))

    # --------------------------------------------------------------------------------
    # Delete a user
    # --------------------------------------------------------------------------------
    def delete_user(self):
        fields = [('deleteAuthorizable', '')]
        if not self.module.check_mode:
            r = requests.post(self.url + '%s.rw.html' % self.path, fields, auth=self.auth)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to delete user: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append("user '%s' deleted" % (self.id))

    # --------------------------------------------------------------------------------
    # Generate a random password
    # --------------------------------------------------------------------------------
    def generate_password(self):
        chars = string.ascii_letters + string.digits + '!@#$%^&*()-_=+.,:;|?'
        self.password = ''
        for i in range(0, 16):
            self.password += random.choice(chars)
        self.msg.append("generated password '%s'" % self.password)

    # --------------------------------------------------------------------------------
    # Check strength of a password
    # Adapted from: http://thelivingpearl.com/2013/01/02/generating-and-checking-passwords-in-python/
    # --------------------------------------------------------------------------------
    def check_password(self):
        score = 0

        if re.search('\d+', self.password):
            score = score + 1
        if re.search('[a-z]', self.password) and re.search('[A-Z]', self.password):
            score = score + 1
        if re.search('.,[,!,@,#,$,%,^,&,*,(,),_,~,-,]', self.password):
            score = score + 1

        if len(self.password)<12 or score < 3:
            self.module.fail_json(
                msg="Password too weak. Minimum length is 12, with characters from three of groups: upper/lower, numeric and special")

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
            first_name=dict(default=None),
            last_name=dict(default=None),
            password=dict(default=None, no_log=True),
            groups=dict(default=None, type='list'),
            admin_user=dict(required=True),
            admin_password=dict(required=True, no_log=True),
            host=dict(required=True),
            port=dict(required=True, type='int'),
        ),
        supports_check_mode=True
    )

    user = AEMUser(module)

    state = module.params['state']

    if state == 'present':
        user.present()
    elif state == 'absent':
        user.absent()
    else:
        module.fail_json(msg='Invalid state: %s' % state)

    user.exit_status()


# --------------------------------------------------------------------------------
# Ansible boiler plate code.
# --------------------------------------------------------------------------------

main()
