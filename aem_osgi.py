#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# Copyright: (c) 2016, Paul Markham <https://github.com/pmarkham>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)


import re
import requests
import yaml
# --------------------------
# Ansible boiler plate code.
# --------------------------
from ansible.module_utils.basic import *

DOCUMENTATION = '''
---
module: aem_osgi
short_description: Manage Adobe AEM osgi settings
description:
    - Create, modify (and delete when implemented) AEM osgi settings
      This module requires pyyaml module to be installed on machine
      running it (this is machine when you run ansible when used as
      local action or target, managed machine when used as regular
      action).
author: Daniel Siechniewicz / nullDowntime Ltd / daniel@nulldowntime.com modified by Paul Markham, Lean Delivery Team .
notes:
    - This module manages bolean, string, array, appending to array and
      factory type settings.
      Deletion (which only makes sense for factory type) is not yet
      implemented.
            id             = dict(required=True),
            state          = dict(required=True, choices=['present', 'absent'])
            property       = dict(default=None)
            value          = dict(default=None)
            osgimode       = dict(default=None)
            admin_user     = dict(required=True)
            admin_password = dict(required=True)
            host           = dict(required=True)
            port           = dict(required=True)

options:
    id:
        description:
            - The AEM OSGI setting ID
        required: true
    state:
        description:
            - Create or delete the group
        required: true
        choices: [present, absent]
       # ABSENT NOT IMPLEMENTED

    property:
        description:
            - Name of the property within specific OSGI id to change. For
              factory it needs to be just 'factory'
        required: false
    value:
        description:
            - Value to set the property to
    osgimode:
        description:
            - "Mode (type) of osgi property: string,array,arrayappend,factory"
    admin_user:
        description:
            - Adobe AEM admin user account name
        required: true
    admin_password:
        description:
            - Adobe AEM admin user account password
        required: true
    url:
        description:
            - Host:Port  that Adobe AEM is listening on
        required: true
'''

EXAMPLES = '''
# Set/modify a string type setting. Use true or false as value
# to set boolean properties.
     - aem_osgi:
         id: com.adobe.cq.cdn.rewriter.impl.CDNRewriter
         property: service.ranking
         value: "5"
         osgimode: string
         state: present
         admin_user: admin
         admin_password: testtest
         url: http://aem-node.example.com:4502

# Create factory type setting
     - aem_osgi:
         id: com.some.osgi.factory.id
         property: "factory"
         value: "{ prop1: value1, prop2: value2, prop3: value3 }"
         osgimode: factory
         state: present
         admin_user: admin
         admin_password: testtest
         url: http://aem-node.example.com:4502

# Create factory logger configuration
     - aem_osgi:
         id: org.apache.sling.commons.log.LogManager.factory.config
         property: "factory"
         value:  "{ 'org.apache.sling.commons.log.level': 'debug',
             'org.apache.sling.commons.log.file': 'logs/standby-qq2.log',
             'org.apache.sling.commons.log.pattern': '{0,date,dd.MM.yyyy HH:mm:ss.SSS} *{4}* [{2}] {3} {5}',
             'org.apache.sling.commons.log.names': ['org.apache.jackrabbit.oak.plugins.segment.standby.store.CommunicationObserver'],
           }"
         osgimode: factory
         state: present
         admin_user: admin
         admin_password: testtest
         url: http://aem-node.example.com:4502

# Set/modify an array type setting - contents of the property will
# be overwritten by array provided in value
     - aem_osgi:
         id: com.adobe.cq.cdn.rewriter.impl.CDNRewriter
         property: cdnrewriter.attributes
         value:
           - python
           - perl
           - pascal
         osgimode: array
         state: present
         admin_user: admin
         admin_password: testtest
         url: http://aem-node.example.com:4502

# Set/modify an array type setting - contents of the property will
# be appended to  array provided in value, idempotently (only once,
# no repeat appending will take place)
     - aem_osgi:
         id: com.adobe.cq.cdn.rewriter.impl.CDNRewriter
         property: cdnrewriter.attributes
         value:
           - pyt
           - pe
         osgimode: arrayappend
         state: present
         admin_user: admin
         admin_password: testtest
         url: http://aem-node.example.com:4502

'''


# -------------
# AEMOsgi class.
# -------------
class AEMOsgi(object):
    def __init__(self, module):
        self.module = module
        self.state = self.module.params['state']
        self.id = self.module.params['id']
        self.property = self.module.params['property']
        self.value = yaml.load(self.module.params['value'])
        self.osgimode = self.module.params['osgimode']
        self.admin_user = self.module.params['admin_user']
        self.admin_password = self.module.params['admin_password']
        self.auth = (self.admin_user, self.admin_password)
        self.url = self.module.params['url']
        self.changed = False
        self.modevalue = {'string': 'value', 'array': 'values',
                          'arrayappend': 'values', 'factory': 'na'}
        self.msg = []
        self.factory_instances = []
        self.curr_props = []
        self.get_osgi_info()
        self.exists = False
        self.factory = []

    # ---------------------
    # Look up package info.
    # ---------------------
    def get_osgi_info(self):
        if self.osgimode in ('string', 'array', 'arrayappend'):

            r = requests.post(
                '%s/system/console/configMgr/%s' % (self.url, self.id),
                auth=self.auth)

            if r.status_code != 200:
                self.module.fail_json(msg='Error searching for osgi id. status\
                =%s output=%s' % (r.status_code, r.text))
            info = r.json()
            self.curr_props = info['properties']
            if self.curr_props[self.property]:
                self.exists = True
            else:
                self.exists = False
        elif self.osgimode in 'factory':
            self.find_factory()
        else:
            self.module.fail_json(
                msg='osgimode %s not recognized' % self.osgimode)

    # -------------------
    # Find factory config
    # -------------------
    def find_factory(self):
        r = requests.get(
            '%s/system/console/config/Configurations.txt' % self.url,
            auth=self.auth)
        if r.status_code != 200:
            self.module.fail_json(msg='Requests failed\
            =%s output=%s' % (r.status_code, r.text))

        instances = re.findall(
            '^PID.*=.*(%s\.[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})\s*$' % self.id,
            r.text, flags=re.M)
        if instances:
            # Instances of a factory found
            factories = {}
            for fi in instances:
                factory_data = re.findall('(PID = %s.*?)\n^PID' % fi, r.text,
                                          flags=re.DOTALL | re.M)
                factory = {}
                for kvp in factory_data[0].splitlines():
                    (k, v) = kvp.strip().split('=')
                    factory[k.strip()] = v.strip()
                factories[fi] = factory
            self.factory_instances = factories
            return True
        else:
            return False

    # ----------------------------------------------------------
    # Check if factory values already match an existing instance
    # ----------------------------------------------------------
    def find_factory_match(self):
        f_match = 0
        factory = ''
        for f, d in self.factory_instances.iteritems():
            v_match = 0
            for k, v in self.value.iteritems():
                if isinstance(v, int):
                    v = str(v)
                # Lists are returned from Configurations.txt without surround\
                # ing quotes
                if isinstance(v, list):
                    v = str(v).replace("'", "")
                if v == d[k]:
                    v_match += 1
            if v_match == len(self.value.keys()):
                f_match += 1
                factory = f

        if f_match == 0:
            return False
        elif f_match == 1:
            self.factory = factory
            return True
        else:
            self.module.fail_json(
                msg='Factory %s matches more than one existing factories, this\
                 SHOULD not happen' % self.id)

    # ---------------------
    # Create factory config
    # ---------------------
    def create_factory(self):
        fields = []
        if self.module.check_mode:
            return

        fields.append(('apply', 'true'))
        fields.append(('action', 'ajaxConfigManager'))
        fields.append(('factoryPid', self.id))
        for k, v in self.value.iteritems():
            if isinstance(v, list):
                for vv in v:
                    fields.append((k, vv))
            else:
                fields.append((k, v))
        fields.append(('propertylist', ','.join(self.value.keys())))

        r = requests.post(
            self.url + '/system/console/configMgr/%5BTemporary%20PID%20replaced%20by%20real%20PID%20upon%20save%5D',
            auth=self.auth, data=fields)

        if r.status_code != 200:
            self.module.fail_json(
                msg='failed to create factory %s: %s - %s' % (self.id,
                                                              r.status_code,
                                                              r.text))

        self.changed = True
        self.find_factory()
        self.find_factory_match()
        self.msg.append('factory %s created' % self.factory)

    # ---------------------
    # Delete factory config
    # ---------------------
    def delete_factory(self):
        fields = []
        if self.module.check_mode:
            return

        fields.append(('delete', 'true'))
        fields.append(('apply', 'true'))

        r = requests.post('%s/system/console/configMgr/%s' % (self.url,
                                                              self.factory),
                          auth=self.auth, data=fields)
        if r.status_code != 200:
            self.module.fail_json(msg='failed to delete %s: %s - %s' %
                                      (self.factory, r.status_code, r.text))

        self.changed = True
        self.msg.append('factory %s deleted' % self.factory)

    # ---------------
    # state 'present'
    # ---------------
    def present(self):

        if self.osgimode in ('factory'):
            if self.factory_instances:
                if self.find_factory_match():
                    self.msg.append('factory %s present' % (self.factory))
                else:
                    self.create_factory()
            else:
                self.create_factory()
        else:
            do_update = False
            if type(self.curr_props[self.property][
                self.modevalue.get(self.osgimode)]) not in (
                    int, bool, str, unicode):
                current = sorted(self.curr_props[self.property][
                    self.modevalue.get(self.osgimode)])
            else:
                current = self.curr_props[self.property][
                    self.modevalue.get(self.osgimode)]

            if self.curr_props[self.property]:
                if self.osgimode == 'arrayappend':
                    combined = sorted(current + self.value)
                    combuniq = sorted(set(combined))
                    self.msg.append(
                        'current %s , combined %s , combuniq %s' % (
                            current, combined, combuniq))
                    if combuniq != current:
                        do_update = True
                elif self.osgimode == 'array' and sorted(current) != sorted(
                        self.value):
                    do_update = True
                elif self.osgimode == 'string' and str(current) != str(
                        self.value):
                    do_update = True
            else:
                self.module.fail_json(
                    msg='No such property %s in %s (curr_props: %s)' % (
                        self.property, self.id, self.curr_props))

            if do_update:
                self.update_property()

    # --------------
    # state 'absent'
    # --------------
    def absent(self):
        if self.osgimode in 'factory':
            if self.factory_instances:
                if self.find_factory_match():
                    self.delete_factory()
                else:
                    self.msg.append('factory already absent')
        else:
            self.module.fail_json(
                msg='State "absent" is not supported yet, sorry')

    # ----------------
    # Update property
    # ----------------
    def update_property(self):
        fields = []
        if self.osgimode not in ['string', 'array', 'arrayappend', 'factory']:
            self.module.fail_json(
                msg='Currently only string, array, arrayappend and factory mo\
                des are supported')
        allpropertylist = ','.join(map(str, self.curr_props.keys()))
        if not self.module.check_mode:
            fields.append(('apply', 'true'))
            fields.append(('action', 'ajaxConfigManager'))
            for i in self.curr_props.keys():
                valueflag = 'value'
                if "values" in self.curr_props[i].keys():
                    valueflag = 'values'
                value = self.curr_props[i][valueflag]
                if i == self.property:
                    if self.osgimode == 'arrayappend':
                        for new_item_value in self.value:
                            if new_item_value not in value:
                                value.append(new_item_value)
#                        value.extend(self.value)
                    else:
                        value = self.value
                fields.append((i, value))

            fields.append(('propertylist', allpropertylist))
            r = requests.post(
                '%s/system/console/configMgr/%s' % (self.url, self.id),
                auth=self.auth, data=fields)

            if r.status_code != 200:
                self.module.fail_json(
                    msg='failed to update property %s in %s: %s - %s' % (
                        self.property, self.id, r.status_code, r.text))
            self.changed = True
            self.msg.append('property updated')

    # ---------------------------------
    # Return status and msg to Ansible.
    # ---------------------------------
    def exit_status(self):
        msg = ','.join(self.msg)
        self.module.exit_json(changed=self.changed, msg=msg)


# ----------
# Mainline.
# ----------
def main():
    module = AnsibleModule(
        argument_spec=dict(
            id=dict(required=True),
            state=dict(required=True, choices=['present', 'absent']),
            property=dict(default=None),
            value=dict(default=None, type='str'),
            osgimode=dict(default=None),
            admin_user=dict(required=True),
            admin_password=dict(required=True, no_log=True),
            url=dict(required=True, type='str')
        ),
        supports_check_mode=True
    )

    osgi = AEMOsgi(module)

    state = module.params['state']

    if state == 'present':
        osgi.present()
    elif state == 'absent':
        osgi.absent()
    else:
        module.fail_json(msg='Invalid state: %s' % state)

    osgi.exit_status()


main()
