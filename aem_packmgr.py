#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)


import json
import xml.etree.ElementTree as ET
import requests
from ansible.module_utils.basic import *

__version__ = '1.0.0'

DOCUMENTATION = '''
---
module: aem_packmgr
author:
  - Lean Delivery Team
short_description: Manage AEM packages
description:
  - Manage AEM packages
'''
EXAMPLES = '''
# Remove package :
    - aem_packmgr:
        state: absent
        pkg_name: test-all
        aem_user: admin
        aem_passwd: admin
        aem_url: http://auth01:4502

# Upload and install a package :
    - aem_packmgr:
        state: present
        pkg_name: test-all
        pkg_path: /home/vagrant/test-all-2.2-SNAPSHOT.zip
        aem_user: admin
        aem_passwd: admin
        aem_url: http://auth01:4502

# Validate package before Upload and install
# https://helpx.adobe.com/experience-manager/6-4/sites/
# administering/using/package-manager.html :

    - aem_packmgr:
        state: present
        pkg_name: test-all
        pkg_validate: true
        pkg_path: /home/vagrant/test-all-2.2-SNAPSHOT.zip
        aem_user: admin
        aem_passwd: admin
        aem_url: http://auth01:4502

'''


def _pgk_exist(url, login, password, int_pkg_name):
    response = requests.get(url + '/crx/packmgr/service.jsp?cmd=ls',
                            auth=(login, password))
    aem_response = ET.fromstring(response.text)

    packages_list = []
    for package in aem_response.findall('response/data/packages/package/name'):
        packages_list.append(package.text)

    download_names = []
    for elements in aem_response.findall(
            'response/data/packages/package/downloadName'):
        download_names.append(elements.text)

    if any(int_pkg_name in x for x in (packages_list, download_names)):
        print('installed')
        return True
    else:
        print('not installed')
        return False


def _pkg_validate(url, login, password, file_name, file_path):
    # validation
    file = {'file': (file_name, open(file_path, 'rb'), 'application/zip')}
    response = requests.post(
        url + '/crx/packmgr/service.jsp?cmd=validate&type=osgiPackageI\
        mports,overlays,acls', files=file, auth=(login, password))
    print(response.text)
    aem_response = ET.fromstring(response.text)
    if (aem_response.find("response/status").attrib['code']) == '200':
        return True
    else:
        return False


def _pkg_install(url, login, password, file_name, file_path, install=False,
                 strict=True):
    # uploading
    files = {'file': (file_name, open(file_path, 'rb'), 'application/zip')}
    values = {'install': install, 'strict': strict}
    response = requests.post(url + '/crx/packmgr/service.jsp', files=files,
                             data=values, auth=(login, password))
    aem_response = ET.fromstring(response.text)
    print('uload finished')
    if (aem_response.find("response/status").attrib['code']) == '200':
        print(response.text)
        int_pkg_name = aem_response.find("response/data/package/name").text
        print("testing result")
        install_status = requests.post(
            url + '/crx/packmgr/service.jsp?cmd=inst&name=' + int_pkg_name,
            auth=(login, password))
        aem_inst_response = ET.fromstring(install_status.text)
        # if failure aem send status code 500 with responce status 200
        if (aem_inst_response.find("response/status").attrib['code']) == '200':
            print('ok')
            return True
        else:
            print(json.dumps({
                "failed": True,
                "msg": install_status.text
            }))
            _pkg_remove(url, login, password, int_pkg_name)
            return False
    else:
        print(json.dumps({
            "failed": True,
            "msg": response.text
        }))
        return False


def _pkg_remove(url, login, password, int_pkg_name):
    response = requests.post(url + '/crx/packmgr/service.jsp?cmd=rm&name=' + int_pkg_name, auth=(login, password))
    aem_response = ET.fromstring(response.text)

    # if failure aem send status code 500 with responce status 200
    if (aem_response.find("response/status").attrib['code']) == '200':
        print('ok')
        return True
    else:
        print('fail')
        return False


def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(default='present', choices=['present', 'absent']),
            pkg_name=dict(type='str'),
            pkg_path=dict(type='str'),
            aem_user=dict(required=True, type='str'),
            aem_passwd=dict(required=True, type='str', no_log=True),
            aem_url=dict(required=True, type='str'),
            aem_force=dict(default='false', type='bool'),
            pkg_validate=dict(default='false', type='bool')
        ),
        supports_check_mode=False
    )

    state = module.params.get('state')
    aem_user = module.params.get('aem_user')
    aem_passwd = module.params.get('aem_passwd')
    aem_url = module.params.get('aem_url')
    aem_force = module.params.get('aem_force')
    pkg_validate = module.params.get('pkg_validate')
    state_changed = False
    message = "no changes"
    pkg_name = module.params.get('pkg_name')
    pkg_path = module.params.get('pkg_path')

    if state in ['present'] and (
            aem_force or not _pgk_exist(aem_url, aem_user, aem_passwd,
                                        pkg_name)):

        if pkg_validate and not _pkg_validate(aem_url, aem_user, aem_passwd,
                                              pkg_name, pkg_path):
            message = "validation of  package " + pkg_name + " is failed"
            module.fail_json(msg=message)

        if _pkg_install(aem_url, aem_user, aem_passwd, pkg_name, pkg_path):

            state_changed = True
            message = "Installation package " + pkg_name + " was successful"
        else:

            message = "Installation package " + pkg_name + " is failed"
            module.fail_json(msg=message)

    if state in ['absent'] and _pgk_exist(aem_url, aem_user, aem_passwd,
                                          pkg_name):

        if _pkg_remove(aem_url, aem_user, aem_passwd, pkg_name):

            state_changed = True
            message = "Removing package " + pkg_name + " was successful"
        else:
            message = "Removing package " + pkg_name + " is failed"
            module.fail_json(msg=message)

    module.exit_json(changed=state_changed, msg=message)


main()
