#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# Copyright: (c) 2016, Paul Markham <https://github.com/pmarkham>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

# Change password for a user.

# Note: you must supply both the old and new passwords for this to work


from ansible.module_utils.basic import *
import requests

DOCUMENTATION = '''
---
module: aem_password
short_description: Change Adobe CQ Password
description:
    - Change Adobe CQ Password
author: Paul Markham, Lean Delivery Team
notes:
    - This is mostly used to change the Admin password from the default of 'admin'.
options:
    id:
        description:
            - The user ID
        required: true
    old_password:
        description:
            - Old password.
        required: true
    new_password:
        description:
            - New password
        required: true
    host:
        description:
            - Host name where Adobe CQ is running
        required: true
    port:
        description:
            - Port number that Adobe CQ is listening on
        required: true
    ignore_err:
        description:
            - Return ok if neither the old nor new passwords are valid for the user.
        required: false
'''

EXAMPLES = '''
# Change admin password from default
- aem_password:
    id: admin
    old_password: admin
    new_password: S3cr3t
    host: "http://localhost"
    port: 4502
'''


# --------------------------------------------------------------------------------
# AEMPassword class.
# --------------------------------------------------------------------------------
class AEMPassword(object):
    def __init__(self, module):
        self.module = module
        self.id = self.module.params['id']
        self.new_password = self.module.params['new_password']
        self.old_password_list = self.module.params['old_password']
        self.ignore_err = self.module.params['ignore_err']
        self.host = str(self.module.params['host'])
        self.port = str(self.module.params['port'])
        self.url = self.host + ':' + self.port

        self.changed = False
        self.msg = []
        self.id_initial = self.id[0]

        self.aem61 = True

        self.get_user_info()

    # --------------------------------------------------------------------------------
    # Look up user info.
    # --------------------------------------------------------------------------------

    def get_user_info(self):
        # check if new password is already valid
        self.msg.append('checking new password')
        if self.aem61:
            r = requests.get(self.url + '/bin/querybuilder.json?path=/home/users&'
                                        '1_property=rep:authorizableId&1_property.value=%s&p.limit=-1'
                             % self.id, auth=(self.id, self.new_password))
        else:
            r = requests.get(self.url + '/home/users/%s/%s.rw.json?props=*'
                             % (self.id_initial, self.id), auth=(self.id, self.new_password))
        if r.status_code == 200:
            self.msg.append("password doesn't need to be changed")
            self.exit_status()

        # check if any of the old passwords are valid
        old_password_valid = False
        for password in self.old_password_list:
            self.msg.append('checking password "%s"' % password)
            if self.aem61:
                r = requests.get(self.url + '/bin/querybuilder.json?path=/home/users&1_property=rep:authorizableId&'
                                            '1_property.value=%s&p.limit=-1'
                                 % self.id, auth=(self.id, password))
            else:
                r = requests.get(self.url + '/home/users/%s/%s.rw.json?props=*'
                                 % (self.id_initial, self.id), auth=(self.id, password))
            if r.status_code == 200:
                old_password_valid = True
                self.old_password = password
                break

        if not old_password_valid:
            if self.ignore_err:
                self.msg.append('Ignoring that neither old nor new passwords are valid')
                self.exit_status()
            self.module.fail_json(msg='Neither old nor new passwords are valid')

    # --------------------------------------------------------------------------------
    # Set new password
    # --------------------------------------------------------------------------------
    def set_password(self):
        if not self.module.check_mode:
            if self.aem61:
                fields = [
                    ('plain', self.new_password),
                    ('verify', self.new_password),
                    ('old', self.old_password),
                ]
                r = requests.post(self.url + '/crx/explorer/ui/setpassword.jsp',
                                  auth=(self.id, self.old_password), data=fields)
            else:
                fields = [
                    (':currentPassword', self.old_password),
                    ('rep:password', self.new_password),
                ]
                r = requests.post(self.url + '/home/users/%s/%s.rw.html'
                                  % (self.id_initial, self.id), auth=(self.id, self.old_password), data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to change password: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append('password changed')

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
            new_password=dict(required=True, no_log=False),
            old_password=dict(required=True, type='list', no_log=False),
            host=dict(required=True),
            port=dict(required=True, type='int'),
            ignore_err=dict(default=False, type='bool'),
        ),
        supports_check_mode=True
    )

    password = AEMPassword(module)

    password.set_password()

    password.exit_status()


# --------------------------------------------------------------------------------
# Ansible boiler plate code.
# --------------------------------------------------------------------------------
main()
