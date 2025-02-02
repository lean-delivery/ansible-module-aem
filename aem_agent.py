#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Lean Delivery Team <team@lean-delivery.com>
# Copyright: (c) 2016, Paul Markham <https://github.com/pmarkham>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.basic import *
import requests
try:
    import HTMLParser
except ImportError:
    from html.parser import HTMLParser

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = u'''
---
module: aem_agent
author:
- Paul Markham
- Lean Delivery Team
short_description: Manage AEM agents
description:
    - Manage AEM replication and flush agents.
options:
    state:
        description:
            - State of agent
        required: true
        choices: [present, absent, enabled, disabled, password]
    name:
        description:
            - agent name
        required: true
        folder:
        description:
            - Folder containing agents. Usually 'agents.author' or 'agents.publish'.
        required: true
    title:
        description:
            - Agent title
        required: false
        default: null
    description:
        description:
            - Agent description
        required: false
        default: null
    transport_uri:
        description:
            - Transport URI
        required: false
        default: null
    transport_user:
        description:
            - Transport user name
        required: false
        default: null
    transport_password:
        description:
            - Password for transport_user
        required: false
        default: null
    agent_user:
        description:
            - Agent user name
        required: false
        default: null
    template:
        description:
            - agent template
        required: false
        default: /libs/cq/replication/templates/agent
    resource_type:
        description:
            - resource type
        required: false
        default: /libs/cq/replication/components/agent
    retry_delay:
        description:
            - retry delay, in milliseconds.
        required: false
        default: 60000
    triggers:
        description:
            - list of triggers. Valid values are no_status_update, no_versioning, on_distribute, triggerDistribute,
              on_modification, triggerModified, on_off_time, on_receive, ignore_default
        required: false
        default: null
    log_level:
        description:
            - Logging level.
        required: false
        default: info
    serialization_type:
        description:
            - Serialization type
        required: false
        default: durbo
    headers:
        description:
            - List of additional headers. Note these should be HTML encoded if you use any special characters, e.g. quotes should
              be specified as &quot;
        required: false
        default: durbo
    connection_close:
        description:
            - Connection close
        required: false
        default: false
        choices: [true, false]
    connection_timeout:
        description:
            - Connection timeout
        required: false
        default: null
    protocol_version:
        description:
            - Protocol version
        required: false
        default: null
    batch_mode:
        description:
            - Batch mode
        required: false
        default: false
        choices: [true, false]
    batch_wait_time:
        description:
            - batch wait time
        required: false
        default: null
    batch_max_size:
        description:
            - batch max size
        required: false
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
# Create agent
- aem_agent:
    name: repl_publish
    state: present
    title: 'replication agent for publish instance'
    folder: 'agent.author'
    transport_uri: 'http://publ01:4503/bin/receive?sling:authRequestLogin=1'
    transport_user: admin
    transport_password: admin
    triggers: 'on_receive,no_versioning'
    admin_user: admin
    admin_password: admin
    host: auth01
    port: 4502
'''


# --------------------------------------------------------------------------------
# AEMAgent class.
# --------------------------------------------------------------------------------
class AEMAgent(object):
    """docstring for AEMAgent"""

    def __init__(self, module):
        self.module = module
        self.state = self.module.params['state']
        self.folder = self.module.params['folder']
        self.name = self.module.params['name']
        self.title = self.module.params['title']
        self.description = self.module.params['description']
        self.transport_uri = self.module.params['transport_uri']
        self.transport_user = self.module.params['transport_user']
        self.transport_password = self.module.params['transport_password']
        self.agent_user = self.module.params['agent_user']
        self.retry_delay = self.module.params['retry_delay']
        self.template = self.module.params['template']
        self.resource_type = self.module.params['resource_type']
        self.triggers = self.module.params['triggers']
        self.log_level = self.module.params['log_level']
        self.serialization_type = self.module.params['serialization_type']
        self.admin_user = self.module.params['admin_user']
        self.admin_password = self.module.params['admin_password']
        self.host = self.module.params['host']
        self.port = str(self.module.params['port'])
        self.connect_timeout = self.module.params['connect_timeout']
        self.protocol_version = self.module.params['protocol_version']
        self.url = self.host + ':' + self.port
        self.auth = (self.admin_user, self.admin_password)

        if self.module.params['headers']:
            html = HTMLParser.HTMLParser()
            headers = html.unescape(self.module.params['headers'])
            self.headers = eval(headers)
        else:
            self.headers = None

        if not self.title:
            self.title = self.name

        if self.module.params['connection_close']:
            self.connection_close = 'true'
        else:
            self.connection_close = 'false'

        if self.module.params['batch_mode']:
            self.batch_mode = 'true'
            self.batch_wait_time = self.module.params['batch_wait_time']
            self.batch_max_size = self.module.params['batch_max_size']
        else:
            self.batch_mode = 'false'
            self.batch_wait_time = ''
            self.batch_max_size = ''

        # handle empty triggers list
        if self.triggers and len(self.triggers) == 1 and self.triggers[0] == "":
            self.triggers = None

        self.changed = False
        self.msg = []

        self.get_agent_info()

        self.trigger_map = {'no_status_update': 'noStatusUpdate',
                            'no_versioning': 'noVersioning',
                            'on_distribute': 'triggerDistribute',
                            'on_modification': 'triggerModified',
                            'on_off_time': 'triggerOnOffTime',
                            'on_receive': 'triggerReceive',
                            'ignore_default': 'triggerSpecific',
                            }
        self.field_map = {}
        for key, value in self.trigger_map.items():
            self.field_map[value] = key

        if self.triggers:
            for t in self.triggers:
                if t not in self.trigger_map:
                    self.module.fail_json(msg="invalid trigger '%s'" % t)

    # --------------------------------------------------------------------------------
    # Look up agent info.
    # --------------------------------------------------------------------------------
    def get_agent_info(self):
        r = requests.get(self.url + '/etc/replication/%s/%s.4.json' % (self.folder, self.name), auth=self.auth)
        if r.status_code == 200:
            self.exists = True
            self.info = r.json()
            if 'enabled' in self.info['jcr:content']:
                self.enabled = self.info['jcr:content']['enabled']
            else:
                self.enabled = 'false'

            if not self.info['jcr:content'].get('jcr:description'):
                self.info['jcr:content']['jcr:description'] = ""
        else:
            self.exists = False

    # --------------------------------------------------------------------------------
    # state='present'
    # --------------------------------------------------------------------------------
    def present(self):
        if self.exists:
            # Update existing agent
            update_required = False
            if self.title != self.info['jcr:content']['jcr:title']:
                update_required = True
                self.msg.append("title updated from '%s' to '%s'" % (self.info['jcr:content']['jcr:title'], self.title))

            if self.description != self.info['jcr:content']['jcr:description']:
                update_required = True
                self.msg.append("description updated from '%s' to '%s'" % (
                    self.info['jcr:content']['jcr:description'], self.description))

            if self.retry_delay != int(self.info['jcr:content']['retryDelay']):
                update_required = True
                self.msg.append("retry_delay updated from '%s' to '%s'" % (
                    self.info['jcr:content']['retryDelay'], self.retry_delay))

            if 'serializationType' not in self.info['jcr:content']:
                self.info['jcr:content']['serializationType'] = ''
            if self.serialization_type != self.info['jcr:content']['serializationType']:
                update_required = True
                self.msg.append("serialization_type updated from '%s' to '%s'" % (
                    self.info['jcr:content']['serializationType'], self.serialization_type))

            if self.template != self.info['jcr:content']['template']:
                update_required = True
                self.msg.append(
                    "template updated from '%s' to '%s'" % (self.info['jcr:content']['template'], self.template))
            if self.transport_uri != self.info['jcr:content']['transportUri']:
                update_required = True
                self.msg.append("transport_uri updated from '%s' to '%s'" % (
                    self.info['jcr:content']['transportUri'], self.transport_uri))

            if 'transportUser' not in self.info['jcr:content']:
                self.info['jcr:content']['transportUser'] = ''
            if not self.transport_user:
                self.transport_user = ""
            if self.transport_user != self.info['jcr:content']['transportUser']:
                update_required = True
                user_changed = True
                self.msg.append("transport_user updated from '%s' to '%s'" % (
                    self.info['jcr:content']['transportUser'], self.transport_user))

            else:
                user_changed = False

            if self.triggers:
                curr_triggers = []
                for field in self.info['jcr:content']:
                    if field in self.field_map and self.info['jcr:content'][field] == 'true':
                        curr_triggers.append(self.field_map[field])
                curr_triggers.sort()
                self.triggers.sort()
                t1 = ','.join(curr_triggers)
                t2 = ','.join(self.triggers)
                if t1 != t2:
                    update_required = True
                    self.msg.append("triggers updated from '%s' to '%s'" % (t1, t2))

            if 'logLevel' not in self.info['jcr:content']:
                self.info['jcr:content']['logLevel'] = 'info'
            if self.log_level != self.info['jcr:content'].get('logLevel'):
                update_required = True
                self.msg.append(
                    "log level updated from '%s' to '%s'" % (self.info['jcr:content']['logLevel'], self.log_level))

            if 'protocolHTTPConnectionClose' not in self.info['jcr:content']:
                self.info['jcr:content']['protocolHTTPConnectionClose'] = 'false'
            if self.connection_close != self.info['jcr:content']['protocolHTTPConnectionClose']:
                update_required = True
                self.msg.append("protocol HTTP close updated from '%s' to '%s'" % (
                    self.info['jcr:content']['protocolHTTPConnectionClose'], self.connection_close))

            if 'protocolConnectTimeout' not in self.info['jcr:content']:
                self.info['jcr:content']['protocolConnectTimeout'] = ''
            if self.connect_timeout != self.info['jcr:content']['protocolConnectTimeout']:
                update_required = True
                self.msg.append("connection timeout updated from '%s' to '%s'" % (
                    self.info['jcr:content']['protocolConnectTimeout'], self.connect_timeout))

            if 'protocolVersion' not in self.info['jcr:content']:
                self.info['jcr:content']['protocolVersion'] = ''
            if self.protocol_version != self.info['jcr:content']['protocolVersion']:
                update_required = True
                self.msg.append("protocol version updated from '%s' to '%s'" % (
                    self.info['jcr:content']['protocolVersion'], self.protocol_version))

            if 'userId' not in self.info['jcr:content']:
                self.info['jcr:content']['userId'] = ''
            if self.agent_user != self.info['jcr:content']['userId']:
                update_required = True
                self.msg.append(
                    "agent user ID updated from '%s' to '%s'" % (self.info['jcr:content']['userId'], self.agent_user))

            if self.serialization_type == 'flush':
                if 'protocolHTTPMethod' not in self.info['jcr:content']:
                    update_required = True
                    self.msg.append("protocol HTTP method set to '%s'" % ('GET'))
                elif self.info['jcr:content']['protocolHTTPMethod'] != 'GET':
                    update_required = True
                    self.msg.append("protocol HTTP method updated from '%s' to '%s'" % (
                        self.info['jcr:content']['protocolHTTPMethod'], 'GET'))

                if self.headers:
                    flush_headers = ','.join(self.headers)
                else:
                    flush_headers = "CQ-Action:{action},CQ-Handle:{path},CQ-Path:{path}"
                if 'protocolHTTPHeaders' not in self.info['jcr:content']:
                    update_required = True
                    self.msg.append("protol HTTP headers'%s'" % (flush_headers))
                else:
                    curr_headers = ','.join(self.info['jcr:content']['protocolHTTPHeaders'])
                    if curr_headers != flush_headers:
                        update_required = True
                        self.msg.append("protol HTTP headers updated from '%s' to '%s'" % (curr_headers, flush_headers))

            if 'queueBatchMode' not in self.info['jcr:content']:
                self.info['jcr:content']['queueBatchMode'] = ''
            if self.batch_mode != self.info['jcr:content']['queueBatchMode']:
                update_required = True
                self.msg.append("batch mode changed from '%s' to '%s'" % (
                    self.info['jcr:content']['queueBatchMode'], self.batch_mode))

            if 'queueBatchWaitTime' not in self.info['jcr:content']:
                self.info['jcr:content']['queueBatchWaitTime'] = ''
            if self.batch_wait_time != self.info['jcr:content']['queueBatchWaitTime']:
                update_required = True
                self.msg.append("batch wait time changed from '%s' to '%s'" % (
                    self.info['jcr:content']['queueBatchWaitTime'], self.batch_wait_time))

            if 'queueBatchMaxSize' not in self.info['jcr:content']:
                self.info['jcr:content']['queueBatchMaxSize'] = ''
            if self.batch_max_size != self.info['jcr:content']['queueBatchMaxSize']:
                update_required = True
                self.msg.append("batch max size changed from '%s' to '%s'" % (
                    self.info['jcr:content']['queueBatchMaxSize'], self.batch_max_size))

            if self.state == 'present':
                self.enable()
            elif self.state == 'enabled':
                self.enable()
            elif self.state == 'disabled':
                self.disable()
            elif self.state == 'password':
                self.password()
            if update_required:
                if not user_changed:
                    self.transport_password = None
                self.define_agent()
            self.msg.append('agent updated')
        else:
            # Create a new agent
            self.define_agent()
            self.msg.append('agent created')

    # --------------------------------------------------------------------------------
    # state='absent'
    # --------------------------------------------------------------------------------
    def absent(self):
        if self.exists:
            self.delete_agent()

    # --------------------------------------------------------------------------------
    # service='enabled'
    # --------------------------------------------------------------------------------
    def enable(self):
        if self.exists:
            self.enable_agent()
        else:
            self.module.fail_json(msg="can't find agent '/etc/replication/%s/%s'" % (self.folder, self.name))

    # --------------------------------------------------------------------------------
    # service='disabled'
    # --------------------------------------------------------------------------------
    def disable(self):
        if self.exists:
            self.disable_agent()
        else:
            self.module.fail_json(msg="can't find agent '/etc/replication/%s/%s'" % (self.folder, self.name))

    # --------------------------------------------------------------------------------
    # service='password'
    # --------------------------------------------------------------------------------
    def password(self):
        if self.exists:
            if not self.transport_password:
                self.module.fail_json(msg='Missing required argument: transport_password')
            self.set_password()
        else:
            self.module.fail_json(msg="can't find agent '/etc/replication/%s/%s'" % (self.folder, self.name))

    # --------------------------------------------------------------------------------
    # Create a new agent
    # --------------------------------------------------------------------------------
    def define_agent(self):
        if not self.transport_uri:
            self.module.fail_json(msg='Missing required argument: transport_uri')

        fields = [
            ('jcr:primaryType', 'cq:Page'),
            ('jcr:content/jcr:title', self.title),
            ('jcr:content/jcr:description', self.description),
            ('jcr:content/sling:resourceType', self.resource_type),
            ('jcr:content/template', self.template),
            ('jcr:content/transportUri', self.transport_uri),
            ('jcr:content/retryDelay', self.retry_delay),
            ('jcr:content/serializationType', self.serialization_type),
            ('jcr:content/logLevel', self.log_level),
            ('jcr:content/protocolHTTPConnectionClose', self.connection_close),
            ('jcr:content/userId', self.agent_user),
            ('jcr:content/protocolConnectTimeout', self.connect_timeout),
            ('jcr:content/protocolVersion', self.protocol_version),
            ('jcr:content/queueBatchMode', self.batch_mode),
            ('jcr:content/queueBatchWaitTime', self.batch_wait_time),
            ('jcr:content/queueBatchMaxSize', self.batch_max_size),
        ]
        if self.transport_user:
            fields.append(('jcr:content/transportUser', self.transport_user))
        if self.transport_password:
            fields.append(('jcr:content/transportPassword', self.transport_password))
        if self.headers:
            fields.append(('jcr:content/protocolHTTPMethod', 'GET'))
            for h in self.headers:
                fields.append(('jcr:content/protocolHTTPHeaders', h))
        else:
            if self.serialization_type == 'flush':
                fields.append(('jcr:content/protocolHTTPMethod', 'GET'))
                fields.append(('jcr:content/protocolHTTPHeaders', 'CQ-Action:{action}'))
                fields.append(('jcr:content/protocolHTTPHeaders', 'CQ-Handle:{path}'))
                fields.append(('jcr:content/protocolHTTPHeaders', 'CQ-Path:{path}'))

        if self.state in ["present", "enabled"]:
            fields.append(('jcr:content/enabled', "true"))
        elif self.state == "disabled":
            fields.append(('jcr:content/enabled', "false"))

        if self.triggers:
            trigger_setting = {}
            for t in self.trigger_map:
                trigger_setting[t] = 'false'
            for t in self.triggers:
                trigger_setting[t] = 'true'
            for k, v in trigger_setting.items():
                fields.append(('jcr:content/%s' % self.trigger_map[k], v))
        if not self.module.check_mode:
            r = requests.post(self.url + '/etc/replication/%s/%s' % (self.folder, self.name), auth=self.auth,
                              data=fields)
            self.get_agent_info()
            if r.status_code < 200 or r.status_code > 299 or not self.exists:
                self.module.fail_json(msg='failed to create agent: %s - %s' % (r.status_code, r.text))
        self.changed = True

    # --------------------------------------------------------------------------------
    # Delete a agent
    # --------------------------------------------------------------------------------
    def delete_agent(self):
        if not self.module.check_mode:
            r_data = {':operation': 'delete'}
            r = requests.post(self.url + '/etc/replication/%s/%s' % (self.folder, self.name), auth=self.auth, data=r_data)
            if r.status_code != 204:
                self.module.fail_json(msg='failed to delete agent: %s - %s' % (r.status_code, r.text))
        self.changed = True
        self.msg.append('agent deleted')

    # --------------------------------------------------------------------------------
    # Enable agent
    # --------------------------------------------------------------------------------
    def enable_agent(self):
        fields = [('jcr:content/enabled', 'true')]
        if not self.module.check_mode and self.enabled != "true":
            r = requests.post(self.url + '/etc/replication/%s/%s' % (self.folder, self.name), auth=self.auth,
                              data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to enable agent: %s - %s' % (r.status_code, r.text))
            self.changed = True
            self.msg.append('agent enabled')
        else:
            self.msg.append('agent already enabled')

    # --------------------------------------------------------------------------------
    # Disable agent
    # --------------------------------------------------------------------------------
    def disable_agent(self):
        fields = [('jcr:content/enabled', 'false')]
        if not self.module.check_mode and self.enabled != "false":
            r = requests.post(self.url + '/etc/replication/%s/%s' % (self.folder, self.name), auth=self.auth,
                              data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to disable agent: %s - %s' % (r.status_code, r.text))
            self.changed = True
            self.msg.append('agent disabled')
        else:
            self.msg.append('agent already disabled')

    # --------------------------------------------------------------------------------
    # Set password
    # --------------------------------------------------------------------------------
    def set_password(self):
        fields = [('jcr:content/transportPassword', self.transport_password)]
        if not self.module.check_mode and self.transport_password != self.info['jcr:content']["transportPassword"]:
            r = requests.post(self.url + '/etc/replication/%s/%s' % (self.folder, self.name), auth=self.auth,
                              data=fields)
            if r.status_code != 200:
                self.module.fail_json(msg='failed to change password: %s - %s' % (r.status_code, r.text))
            self.changed = True
            self.msg.append('password changed')
        else:
            self.msg.append('old password equal to new')

    # --------------------------------------------------------------------------------
    # Return status and msg to Ansible.
    # --------------------------------------------------------------------------------
    def exit_status(self):
        if self.changed:
            msg = ','.join(self.msg)
            self.module.exit_json(changed=True, msg=msg)
        else:
            self.module.exit_json(changed=False)


# --------------------------------------------------------------------------------
# Mainline.
# --------------------------------------------------------------------------------
def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(required=True, choices=['present', 'absent', 'enabled', 'disabled', 'password']),
            folder=dict(required=True),
            name=dict(required=True),
            title=dict(default=None),
            description=dict(default=None),
            transport_uri=dict(default=None),
            transport_user=dict(default=None),
            transport_password=dict(default=None, no_log=True),
            agent_user=dict(default=''),
            template=dict(default='/libs/cq/replication/templates/agent'),
            resource_type=dict(default='/libs/cq/replication/components/agent'),
            retry_delay=dict(default=60000, type='int'),
            triggers=dict(default=None, type='list'),
            log_level=dict(default='info'),
            serialization_type=dict(default='durbo'),
            admin_user=dict(required=True),
            admin_password=dict(required=True, no_log=True),
            host=dict(required=True),
            port=dict(required=True, type='int'),
            headers=dict(default=None),
            connection_close=dict(default=False, type='bool'),
            connect_timeout=dict(default=''),
            protocol_version=dict(default=''),
            batch_mode=dict(default=False, type='bool'),
            batch_wait_time=dict(default=''),
            batch_max_size=dict(default='')
        ),
        supports_check_mode=True
    )

    agent = AEMAgent(module)

    state = module.params['state']

    if state in ['present', 'enabled', 'disabled', 'password']:
        agent.present()
    elif state == 'absent':
        agent.absent()
    else:
        module.fail_json(msg='Invalid state: %s' % state)

    agent.exit_status()


# --------------------------------------------------------------------------------
# Ansible boiler plate code.
# --------------------------------------------------------------------------------

main()
