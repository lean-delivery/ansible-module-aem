#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# Copyright: (c) 2016, Paul Markham <https://github.com/pmarkham>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

# Hash a password to a SHA256, base 64 encoded value. Return it as an Ansible fact

from ansible.module_utils.basic import *
import sys
import os
import hashlib
import base64


def main():
    module = AnsibleModule(
        argument_spec=dict(
            user=dict(required=True),
            password=dict(required=True, no_log=True),
        ),
        supports_check_mode=True
    )

    hash = base64.b64encode(hashlib.sha256(module.params['password']).digest())
    key = '%s_password_sha256' % module.params['user']
    facts = {
        key: hash
    }

    module.exit_json(ansible_facts=facts)


# --------------------------------------------------------------------------------
# Ansible boiler plate code.
# --------------------------------------------------------------------------------
main()
