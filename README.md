# Adobe Experience Manager (AEM) Ansible modules

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=flat)](https://raw.githubusercontent.com/lean-delivery/ansible-modules-aem/master/LICENSE)
[![Build Status](https://travis-ci.org/lean-delivery/ansible-modules-aem.svg?branch=master)](https://travis-ci.org/lean-delivery/ansible-modules-aem)

## How to install this modules:
---

### Default installation:

```bash
ansible-pull -U https://github.com/lean-delivery/ansible-modules-aem install-modules.yml
```

### Specify version / commit / tag:

```bash
ansible-pull -U https://github.com/lean-delivery/ansible-modules-aem -e modules_version=<tagname> install-modules.yml
```

### Installation as a part of playbook:
```yaml
---
- hosts: localhost
  gather_facts: False
  vars:
    repo_url: "{{ lookup('env','repo_url') | default('https://github.com/lean-delivery/ansible-modules-aem.git', true)}}"
    modules_path: "{{ lookup('env','ansible_modules_path') | default('~/.ansible/plugins/modules', true)}}"
    modules_version: "{{ lookup('env','ansible_modules_version') | default('master', true)}}"
  tasks:
    - name: Make sure that modules directory exists
      file:
        path: "{{ modules_path }}"
        state: directory
        mode: 0755
    - name: Install Ansible AEM Modules
      git:
        repo: "{{ repo_url }}"
        dest: "{{ modules_path }}/ansible-modules-aem"
        version: "{{ modules_version }}"
        force: yes 
```

## License

GNU General Public License v3.0

## Authors

Original version: [Paul Markham](https://github.com/pmarkham/ansible-adobe-aem)

Current version: team@lean-delivery.com
