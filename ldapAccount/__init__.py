#!/usr/bin/python
## vim: set ts=2 sw=2 noai noet
##
## purpose: LDAP Samba user, group and computer account management
## copyright: B1 Systems GmbH <info@b1-systems.de>, 2011.
## modifications by: Arnaud Loonstra <arnaud@sphaero.org>, 2012.
## license: GPLv3+, http://www.gnu.org/licenses/gpl-3.0.html
## author: Uwe Grawert <grawert@b1-systems.de>, 2011.
## author: Arnaud Loonstra <arnaud@sphaero.org>, 2012
## version: 0.2: user,group,computer management 20121019.
##
## TODO:
## - syntax check the configuration file ldapsmb.conf
## - add AIX user creation

import os
import sys
import re
import ldap
import ldap.modlist
import ConfigParser
import optparse
import getpass
import time
import random
import base64
import hashlib
import binascii
import crypt

# path to configuration file
cfgfile = "/etc/ldapsmb.conf"
# use config override if exists
if os.path.exists( os.path.join(os.path.expanduser("~"), ".ldapsmb.conf" )):
    cfgfile = os.path.join(os.path.expanduser("~"), ".ldapsmb.conf" )

class Config(ConfigParser.ConfigParser):
    '''Provide configuration parameters from external config file'''
    def __init__(self, filename):
        ConfigParser.ConfigParser.__init__(self)	
        self.read(filename)

    def getOption(self, section, option):
        try:
            return self.get(section, option)
        except ConfigParser.NoOptionError, e:
            return None

    def getOp(self, section, option):
        return self.getOption(section, option)

    def printOptions(self):
        for section in self.sections():
            print section
            for pairs in self.items(section):
                print pairs

class LDAP(object):
    '''LDAP connection'''
    def __init__(self, uri, binddn, passwd, usetls):
        self.ldap_session = self.connect(uri, binddn, passwd, usetls)

    def connect(self, uri, binddn, passwd, usetls):
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        session = ldap.initialize(uri)

        if usetls:
            session.start_tls_s()

        session.simple_bind(binddn, passwd)
        return session

    def ldap_add(self, dn, attrs):
        self.ldap_session.add_s(dn, attrs)

    def ldap_del(self, dn):
        self.ldap_session.delete_s(dn)

    def ldap_search(self, basedn, filter, attributes, scope=ldap.SCOPE_SUBTREE):
        result_id  = self.ldap_session.search(basedn, scope, filter, attributes)
        type, result_list = self.ldap_session.result(result_id, 1)
        return result_list

    def ldap_update_attribute(self, dn, attribute, values):
        attrs = [(ldap.MOD_REPLACE, attribute, values)]
        self.ldap_session.modify_s(dn, attrs)

    def ldap_add_attribute(self, dn, attribute, values):
        attrs = [(ldap.MOD_ADD, attribute, values)]
        self.ldap_session.modify_s(dn, attrs)

    def ldap_del_attribute(self, dn, attribute, values):
        attrs = [(ldap.MOD_DELETE, attribute, values)]
        self.ldap_session.modify_s(dn, attrs)

class Account(LDAP):
    '''Management of user account data in LDAP'''
    def __init__(self, configFile):
        self.cfg = Config(configFile)
        uri      = self.cfg.getOp('ldap', 'uri')
        binddn   = self.cfg.getOp('ldap', 'binddn')
        passwd   = self.cfg.getOp('ldap', 'passwd')
        usetls   = self.cfg.getboolean('ldap', 'usetls')
        
        super(Account, self).__init__(uri, binddn, passwd, bool(usetls))

    def getNextFreeUid(self):
        suffix = self.cfg.getOp('samba', 'ldap suffix')
        domain = self.cfg.getOp('samba', 'sambaDomain')
        filter = 'sambaDomainName=' + domain
        uid    = None

        result = self.ldap_search(suffix, filter, ['uidNumber'])
        
        if result:
            uid = result[0][1]['uidNumber'][0]
        else:
            raise("can't find next free uid")
            
        return uid

    def setNextFreeUid(self, uid):
        suffix = self.cfg.getOp('samba', 'ldap suffix')
        domain = self.cfg.getOp('samba', 'sambaDomain')

        dn = 'sambaDomainName=%s,%s' % (domain, suffix)
        self.ldap_update_attribute(dn, 'uidNumber', uid)

    def getNextFreeGid(self):
        suffix = self.cfg.getOp('samba', 'ldap suffix')
        domain = self.cfg.getOp('samba', 'sambaDomain')
        filter = 'sambaDomainName=' + domain
        gid    = None

        result = self.ldap_search(suffix, filter, ['gidNumber'])

        if result:
            gid = result[0][1]['gidNumber'][0]

        return gid

    def setNextFreeGid(self, gid):
        suffix = self.cfg.getOp('samba', 'ldap suffix')
        domain = self.cfg.getOp('samba', 'sambaDomain')

        dn = 'sambaDomainName=%s,%s' % (domain, suffix)
        self.ldap_update_attribute(dn, 'gidNumber', str(gid))

    def getNextFreeRid(self):
        suffix = self.cfg.getOp('samba', 'ldap suffix')
        domain = self.cfg.getOp('samba', 'sambaDomain')
        filter = 'sambaDomainName=' + domain
        rid    = None

        result = self.ldap_search(suffix, filter, ['sambaNextRid'])

        if result:
            rid = result[0][1]['sambaNextRid'][0]

        return rid

    def setNextFreeRid(self, rid):
        suffix = self.cfg.getOp('samba', 'ldap suffix')
        domain = self.cfg.getOp('samba', 'sambaDomain')

        dn = 'sambaDomainName=%s,%s' % (domain, suffix)
        self.ldap_update_attribute(dn, 'sambaNextRid', rid)

    def getUserUid(self, username):
        suffix      = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix = self.cfg.getOp('samba', 'ldap user suffix')
        search_dn   = '%s,%s' % (user_suffix, suffix)
        filter      = 'uid=%s' % (username)
        uid         = None

        result = self.ldap_search(search_dn, filter, ['uidNumber'])

        if result:
            uid = result[0][1]['uidNumber'][0]

        return uid

    def getUserGid(self, username):
        suffix      = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix = self.cfg.getOp('samba', 'ldap user suffix')
        search_dn   = '%s,%s' % (user_suffix, suffix)
        filter      = 'uid=%s' % (username)
        gid         = None

        result = self.ldap_search(search_dn, filter, ['gidNumber'])

        if result:
            gid = result[0][1]['gidNumber'][0]

        return gid
    
    def getGidName(self, gid):
        suffix      = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')
        search_dn   = '%s,%s' % (group_suffix, suffix)
        filter      = 'gidNumber=%s' % (gid)
        groupName   = None

        result = self.ldap_search(search_dn, filter, ['cn'])

        if result:
            groupName = result[0][1]['cn'][0]

        return groupName

    def getDomainSID(self):
        suffix = self.cfg.getOp('samba', 'ldap suffix')
        domain = self.cfg.getOp('samba', 'sambaDomain')
        filter = 'sambaDomainName=' + domain
        sid    = None

        result = self.ldap_search(suffix, filter, ['sambaSID'])

        if result:
            sid = result[0][1]['sambaSID'][0]

        return sid

    def createSambaDomain(self, suffix=None, domainName=None, sambaSID=None,
                          nextFreeUid=None, nextFreeGid=None, nextFreeRid=None,
                          minPwdLength=None, minPwdAge=None, maxPwdAge=None,
                          pwdHistoryLength=None, lockoutThreshold=None,
                          logonToChgPwd=None, refuseMachinePwdChange=None):
        suffix           = self.cfg.getOp('samba', 'ldap suffix')
        domainName       = self.cfg.getOp('samba', 'sambaDomain')
        sambaSID         = self.cfg.getOp('samba', 'sambaSID')
        nextFreeUid      = self.cfg.getOp('samba', 'uid')
        nextFreeGid      = self.cfg.getOp('samba', 'gid')
        nextFreeRid      = self.cfg.getOp('samba', 'rid')
        pwdHistoryLength = self.cfg.getOp('samba', 'pwdHistoryLength')
        minPwdAge        = self.cfg.getOp('samba', 'minPwdAge')
        maxPwdAge        = self.cfg.getOp('samba', 'maxPwdAge')
        lockoutThreshold = self.cfg.getOp('samba', 'lockoutThreshold')
        logonToChgPwd    = self.cfg.getOp('samba', 'logonToChgPwd')

        if not nextFreeUid:
            nextFreeUid = '1000'
        if not nextFreeGid:
            nextFreeGid = '1000'
        if not nextFreeRid:
            nextFreeRid = '1000'
        if not minPwdAge:
            minPwdAge = '0'
        if not maxPwdAge:
            maxPwdAge = '0'
        if not minPwdLength:
            minPwdLength = '0'
        if not pwdHistoryLength:
            pwdHistoryLength = '0'
        if not lockoutThreshold:
            lockoutThreshold = '0'
        if not logonToChgPwd:
            logonToChgPwd = '0'
        if not refuseMachinePwdChange:
            refuseMachinePwdChange = '0'

        objClasses = ['top', 'sambaDomain', 'sambaUnixIdPool']
        dn         = 'sambaDomainName=' + domainName + ',' + suffix

        attrs = [
                    ('objectClass', objClasses),
                    ('sambaDomainName', [domainName]),
                    ('sambaSID', [sambaSID]),
                    ('uidNumber', [nextFreeUid]),
                    ('gidNumber', [nextFreeGid]),
                    ('sambaNextRid', [nextFreeRid]),
                    ('sambaMinPwdAge', [minPwdAge]),
                    ('sambaMaxPwdAge', [maxPwdAge]),
                    ('sambaMinPwdLength', [minPwdLength]),
                    ('sambaPwdHistoryLength', [pwdHistoryLength]),
                    ('sambaLockoutThreshold', [lockoutThreshold]),
                    ('sambaRefuseMachinePwdChange', [refuseMachinePwdChange]),
                    ('sambaLogonToChgPwd', [logonToChgPwd])
                ]

        try:
            self.ldap_add(dn, attrs)
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': No such object!'
        except ldap.INVALID_DN_SYNTAX, e:
            print dn + ': Invalid DN syntax. Is samba3 schema installed?'
        except ldap.LDAPError, e:
            print dn + ':', e.args

    def createSambaGroup(self, name, gid, sambaSID=None, description=None,
                         sambaGroupType=None):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')
        objClasses   = ['top', 'namedObject', 'posixGroup', 'sambaGroupMapping']

        if not gid:
            gid = self.getNextFreeGid()
        if not sambaSID:
            sambaSID = self.getDomainSID()
            sambaSID = sambaSID + '-' + gid

        if not description:
            description = ' '

        if not sambaGroupType:
            sambaGroupType = '2'    # domain group

        dn    = 'cn=%s,%s,%s' % (name, group_suffix, suffix)

        attrs = [
                    ('objectClass', objClasses ),
                    ('cn', [name]),
                    ('displayName', [name]),
                    ('description', [description]),
                    ('gidNumber', [gid]),
                    ('sambaSID', [sambaSID]),
                    ('sambaGroupType', [sambaGroupType])
                ]

        try:
            self.ldap_add(dn, attrs)
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': No such object!'
        except ldap.INVALID_SYNTAX, e:
            print dn + ': Invalid attribute syntax. Is samba3 schema installed?'
        except ldap.LDAPError, e:
            print dn + ': ', e.args
        else:
            self.setNextFreeGid(int(gid) + 1)

    def createPosixGroup(self, name, gid, description=None):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')
        objClasses   = ['top', 'posixGroup']

        if not gid:
            gid = self.getNextFreeGid()

        if not description:
            description = ' '

        dn    = 'cn=%s,%s,%s' % (name, group_suffix, suffix)

        attrs = [
                    ('objectClass', objClasses ),
                    ('cn', [name]),
                    ('description', [description]),
                    ('gidNumber', [gid])
                ]

        try:
            self.ldap_add(dn, attrs)
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': No such object!'
        except ldap.INVALID_SYNTAX, e:
            print dn + ': Invalid attribute syntax'
        except ldap.LDAPError, e:
            print dn + ': ', e.args
        else:
            self.setNextFreeGid(int(gid) + 1)

    def deleteGroup(self, name):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')

        dn = 'cn=%s,%s,%s' % ( name, group_suffix, suffix )

        try:
            self.ldap_del(dn)
            print dn + ': Successfully deleted'
        except ldap.LDAPError, e:
            print dn + ': ', e.args

    def modifyGroup(self, name, attribute, value):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')

        dn = 'cn=%s,%s,%s' % ( name, group_suffix, suffix )

        try:
            self.ldap_update_attribute(dn, attribute, [value])
            print '%s: Successfully changed %s' % (dn, attribute)
        except ldap.LDAPError, e:
            print dn + ': ', e.args

    def createAixUser(self, name, uid=None, gid=None, home=None,
                      loginShell=None):
        #TODO: create AIX account entry
        pass

    def createPosixUser(self, name, **kwargs):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix  = self.cfg.getOp('samba', 'ldap user suffix')
        objClasses   = ['top', 'person', 'organizationalPerson',
                         'inetOrgPerson', 'posixAccount', 'shadowAccount']

        # set defaults
        uid                 = kwargs.pop('uid', None)
        if not uid:
            uid = self.getNextFreeUid()
            self.setNextFreeUid(str(int(uid)+1))
        gid                 = kwargs.pop('uid', self.cfg.getOp('posix', 'defaultGidNumber'))
        defHomePath = self.cfg.getOp('posix', 'homeDirPath')
        home                = kwargs.pop('home', defHomePath + "/" + name)
        loginShell          = kwargs.pop('loginShell', None)
        if not loginShell:
            loginShell = self.cfg.getOp('posix', 'defaultShell')
        givenName           = kwargs.pop('givenName', name)
        sn                  = kwargs.pop('sn', name)
        
        dn = 'uid=%s,%s,%s' % (name, user_suffix, suffix)

        attrs = {
                'objectClass': objClasses,
                'cn': givenName + " " + sn,
                'givenName': givenName,
                'sn': sn,
                'uid': name,
                'uidNumber': uid,
                'gidNumber': gid,
                'displayName': givenName + " " + sn,
                'gecos': givenName + " " + sn,
                'homeDirectory': home,
                'loginShell': loginShell,
                }
        
        #append remaing values, filter None values
        for key,value in kwargs.iteritems():
            if not value == None:
                attrs[key] = value
        addAttrs = ldap.modlist.addModlist(attrs)
        try:
            self.ldap_add(dn, addAttrs)
            self.setNextFreeUid(str(int(uid) + 1))
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': No such object!'
        except ldap.LDAPError, e:
            print dn + ':', e.args

        #finally add user to it's primaryGroup
        group = self.getGidName(gid)
        if group:
            self.addUserToGroup(name, group)

    def createSambaUser(self, name, **kwargs):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix  = self.cfg.getOp('samba', 'ldap user suffix')
        objClasses   = ['top', 'person', 'organizationalPerson', 'inetOrgPerson',
                         'sambaSamAccount', 'posixAccount', 'shadowAccount']

        # set defaults
        uid                 = kwargs.pop('uid', None)
        if not uid:
            uid = self.getNextFreeUid()
        gid                 = kwargs.pop('uid', self.cfg.getOp('posix', 'defaultGidNumber'))
        defHomePath = self.cfg.getOp('posix', 'homeDirPath')
        home                = kwargs.pop('home', defHomePath + "/" + name)
        loginShell          = kwargs.pop('loginShell', None)
        if not loginShell:
            loginShell = self.cfg.getOp('posix', 'defaultShell')
        givenName           = kwargs.pop('givenName', name)
        sn                  = kwargs.pop('sn', name)
        sambaSID            = kwargs.pop('sambaSID', None)
        if not sambaSID:
            rid = self.getNextFreeRid()
            sambaSID = self.getDomainSID() + '-' + rid
        sambaAcctFlags   = kwargs.pop('sambaAcctFlags', '[U          ]')
        
        dn = 'uid=%s,%s,%s' % (name, user_suffix, suffix)

        attrs = {
                'objectClass': objClasses,
                'cn': givenName + " " + sn,
                'givenName': givenName,
                'sn': sn,
                'uid': name,
                'uidNumber': uid,
                'gidNumber': gid,
                'displayName': givenName + " " + sn,
                'gecos': givenName + " " + sn,
                'homeDirectory': home,
                'loginShell': loginShell,
                'sambaSID': sambaSID,
                'sambaAcctFlags': sambaAcctFlags
                }
                
        #append remaing values, filter None values
        for key,value in kwargs.iteritems():
            if not value == None:
                attrs[key] = value

        addAttrs = ldap.modlist.addModlist(attrs)
        try:
            self.ldap_add(dn, addAttrs)
            self.setNextFreeUid(str(int(uid)+1))
            self.setNextFreeRid(str(int(rid)+1))
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': No such object!'
        except ldap.INVALID_SYNTAX, e:
            print dn + ': Invalid attribute syntax. Is samba3 schema installed?'
        except ldap.LDAPError, e:
            print dn + ':', e.args
            
        #finally add user to it's primaryGroup
        group = self.getGidName(gid)
        if group:
            self.addUserToGroup(name, group)

    def modifyUser(self, name, attribute, value):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix  = self.cfg.getOp('samba', 'ldap user suffix')

        dn = 'uid=%s,%s,%s' % (name, user_suffix, suffix)

        try:
            self.ldap_update_attribute(dn, attribute, [value])
            print '%s: Successfully changed %s' % (dn, attribute)
        except ldap.LDAPError, e:
            print dn + ': ', e.args

    def deleteUser(self, name):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix  = self.cfg.getOp('samba', 'ldap user suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')

        user_dn       = 'uid=%s,%s,%s' % ( name, user_suffix, suffix)
        search_suffix = '%s,%s' % ( group_suffix, suffix)
        filter        = 'memberUid=' + name
        group_dns     = []

        # search groups where user is a member
        result = self.ldap_search(search_suffix, filter, ['cn'])

        for idx, result in enumerate(result):
            group_dns.append( result[0] )

        try:
            for group_dn in group_dns:
                self.ldap_del_attribute(group_dn, 'memberUid', [name])
                print '%s: Successfully removed member %s' % (group_dn, name)

            self.ldap_del(user_dn)
            print user_dn + ': Successfully deleted'
        except ldap.NO_SUCH_OBJECT, e:
            print user_dn + ': No such object!'
        except ldap.LDAPError, e:
            print e

    def createPosixMachine(self, name, uid=None, gid=None, displayName=None,
                           gecos=None, loginShell='/bin/false', home='/dev/null'):
        suffix         = self.cfg.getOp('samba', 'ldap suffix')
        machine_suffix = self.cfg.getOp('samba', 'ldap machine suffix')
        objClasses     = ['top', 'person', 'organizationalPerson',
                           'inetOrgPerson', 'posixAccount']

        # append '$' to the end of the name, marking it as a machine
        m = re.match('.*\$$', name)
        if not m:
            name = name + '$'

        if not uid:
            uid = self.getNextFreeUid()
            self.setNextFreeUid(str(int(uid) + 1))
        if not gid:
            gid = '515' # 'Domain Computers'
        if not displayName:
            displayName = name.upper()
        if not gecos:
            gecos = 'Computer'

        dn = 'uid=%s,%s,%s' % (name, machine_suffix, suffix)

        attrs = [
            ("objectClass", objClasses ),
            ('cn', [name]),
            ('sn', [name]),
            ('uid', [name]),
            ('displayName', [displayName]),
            ('gecos', [gecos]),
            ('uidNumber', [uid]),
            ('gidNumber', [gid]),
            ('loginShell', [loginShell]),
            ('homeDirectory', [home])
        ]

        try:
            self.ldap_add(dn, attrs)
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': No such object!'
        except ldap.LDAPError, e:
            print dn + ':', e.args

            samba.createSambaMachine(options.name, options.uidNumber,
                                     options.gidNumber, options.displayName,
                                     options.sambaSID)

    def createSambaMachine(self, name, uid=None, gid=None, displayName=None,
                           sambaSID=None, sambaPrimaryGroupSID=None,
                           gecos=None, loginShell='/bin/false', home='/dev/null',
                           sambaAcctFlags=None):
        suffix         = self.cfg.getOp('samba', 'ldap suffix')
        machine_suffix = self.cfg.getOp('samba', 'ldap machine suffix')
        objClasses     = ['top', 'person', 'organizationalPerson',
                           'inetOrgPerson', 'posixAccount', 'sambaSamAccount']

        # append '$' to the end of the name, marking it as a machine
        m = re.match('.*\$$', name)
        if not m:
            name = name + '$'

        # set defaults
        if not uid:
            uid = self.getNextFreeUid()
        if not gid:
            gid = '515' # 'Domain Computers'
        if not sambaSID:
            sambaSID = self.getDomainSID() + '-' + uid
        if not sambaPrimaryGroupSID:
            sambaPrimaryGroupSID = self.getDomainSID() + '-' + gid
        if not displayName:
            displayName = name.upper()
        if not gecos:
            gecos = 'Computer'
        if not sambaAcctFlags:
            sambaAcctFlags = '[W          ]'

        dn = 'uid=%s,%s,%s' % (name, machine_suffix, suffix)

        attrs = [
            ("objectClass", objClasses ),
            ('cn', [name]),
            ('sn', [name]),
            ('uid', [uid]),
            ('displayName', [displayName]),
            ('gecos', [gecos]),
            ('uidNumber', [uid]),
            ('gidNumber', [gid]),
            ('sambaSID', [sambaSID]),
            ('sambaPrimaryGroupSID', [sambaPrimaryGroupSID]),
            ('sambaAcctFlags', [sambaAcctFlags]),
            ('loginShell', [loginShell]),
            ('homeDirectory', [home])
        ]

        try:
            self.ldap_add(dn, attrs)
            self.setNextFreeUid(str(int(uid) + 1))
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': No such object!'
        except ldap.INVALID_SYNTAX, e:
            print dn + ': Invalid attribute syntax. Is samba3 schema installed?'
        except ldap.LDAPError, e:
            print dn + ':', e.args

    def modifyMachine(self, name, attribute, value):
        suffix         = self.cfg.getOp('samba', 'ldap suffix')
        machine_suffix = self.cfg.getOp('samba', 'ldap machine suffix')

        # appending '$' to the end of the name, marks it as a machine
        m = re.match('.*\$$', name)
        if not m:
            name = name + '$'

        dn = 'uid=%s,%s,%s' % (name, machine_suffix, suffix)

        try:
            self.ldap_update_attribute(dn, attribute, [value])
            print '%s: Successfully changed %s' % (dn, attribute)
        except ldap.LDAPError, e:
            print dn + ': ', e.args

    def deleteMachine(self, name):
        suffix         = self.cfg.getOp('samba', 'ldap suffix')
        machine_suffix = self.cfg.getOp('samba', 'ldap machine suffix')

        # appending '$' to the end of the name, marks it as a machine
        m = re.match('.*\$$', name)
        if not m:
            name = name + '$'

        dn = 'uid=%s,%s,%s' % (name, machine_suffix, suffix)

        try:
            self.ldap_del(dn)
            print dn + ': Successfully deleted'
        except ldap.LDAPError, e:
            print dn + ': ', e.args

    def addUserToGroup(self, username, groupname):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')

        dn = 'cn=%s,%s,%s' % (groupname, group_suffix, suffix)

        try:
            self.ldap_add_attribute(dn, 'memberUid', username)
            print '%s: Successfully added %s' % (dn, username)
        except ldap.TYPE_OR_VALUE_EXISTS, e:
            print '%s: %s is already a member' % (dn, username)
        except ldap.LDAPError, e:
            print dn + ': ', e.args

    def deleteUserFromGroup(self, username, groupname):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')

        dn = 'cn=%s,%s,%s' % (groupname, group_suffix, suffix)

        try:
            self.ldap_del_attribute(dn, 'memberUid', username)
            print '%s: Successfully removed %s' % (dn, username)
        except ldap.NO_SUCH_ATTRIBUTE, e:
            print '%s: %s is not a member' % (dn, username)
        except ldap.LDAPError, e:
            print dn + ': ', e, e.args

    def createNTPassword(self, password):
        hash = hashlib.new('md4', password.encode('utf-16le')).digest()
        return binascii.hexlify(hash)

    def createCryptPassword(self, password, digest='SSHA'):
        digest = digest.upper()
        crypt  = password
        salt   = ''

        for i in range(8):
            salt += chr(random.randint(0, 255))

        if digest == "SSHA":
            crypt = "{SSHA}" + base64.encodestring(hashlib.sha1(password+salt).digest()+salt)
        elif digest == "SHA":
            crypt = "{SHA}" + base64.encodestring(hashlib.sha1(password).digest())
        elif digest == "MD5":
            crypt = "{MD5}" + base64.encodestring(hashlib.md5(password).digest())
        elif digest == "CRYPT":
            crypt = "{CRYPT}" + crypt.crypt(password, salt)

        return crypt

    def changeUserPassword(self, username, password, canChangePwd=None, mustChangePwd=None):
        suffix        = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix   = self.cfg.getOp('samba', 'ldap user suffix')
        ntpassword    = self.createNTPassword(password)
        cryptpassword = self.createCryptPassword(password)
        rightNow      = int(time.time())

        if canChangePwd:
            canChangePwd = str(int(canChangePwd) *3600*24 + rightNow)
        else:
            canChangePwd = '0'

        if mustChangePwd:
            mustChangePwd = str(int(mustChangePwd) *3600*24 + rightNow)
        else:
            mustChangePwd = str(90*3600*24 + rightNow)  # default to 90 days

        shadowLastChange = str(rightNow/3600/24)        # days since Unix epoch
        sambaPwdLastSet  = str(rightNow)            # seconds since Unix epoch

        dn = 'uid=%s,%s,%s' % (username, user_suffix, suffix)

        try:
            self.ldap_update_attribute(dn, 'UserPassword', cryptpassword)
            self.ldap_update_attribute(dn, 'shadowLastChange', shadowLastChange)
            self.ldap_update_attribute(dn, 'shadowExpire', mustChangePwd)
            print dn + ': Successfully changed Unix password'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': does not exist!'
        except ldap.LDAPError, e:
            print dn + ': ', e, e.args

        try:
            self.ldap_update_attribute(dn, 'sambaNTPassword', ntpassword)
            self.ldap_update_attribute(dn, 'sambaPwdLastSet', sambaPwdLastSet)
            self.ldap_update_attribute(dn, 'sambaPwdMustChange', mustChangePwd)
            self.ldap_update_attribute(dn, 'sambaPwdCanChange', canChangePwd)
            print dn + ': Successfully changed Samba password'
        except ldap.NO_SUCH_OBJECT, e:
            print dn + ': does not exist!'
        except ldap.OBJECT_CLASS_VIOLATION, e:
            # this exception is raised when object class is not sambaSamAccount
            print dn + ': Not a samba account - Samba password not changed'
        except ldap.UNDEFINED_TYPE, e:
            #FIXME: find a better way of printing exception info
            print dn + ': ' + e[0]['info'] + '. Is samba3 schema installed?'
        except ldap.LDAPError, e:
            print dn + ': ', e, e.args

class Population(object):
    '''Populate LDAP directory with initial Samba configuration,
       domain groups, and basic users'''
    def __init__(self, configFile):
        self.cfg = Config(configFile)
        self.smb = Account(configFile)

    def createSambaDomain(self):
        self.smb.createSambaDomain()

    def createSambaUsers(self):
        suffix      = self.cfg.getOp('samba', 'ldap suffix')
        user_suffix = self.cfg.getOp('samba', 'ldap user suffix')
        sambaSID    = self.cfg.getOp('samba', 'sambaSID')

        users = {
            'root': {
                'uid': '0',
                'gid': '0',
                'sambaSID': sambaSID + '-' + '500',
                'sambaPrimaryGroupSID': sambaSID + '-' + '512',
                'displayName': 'Domain Administrator',
                'acctFlags': '[UX         ]'
            },
            'nobody': {
                'uid': '999',
                'gid': '514',
                'sambaSID': sambaSID + '-' + '514',
                'sambaPrimaryGroupSID': sambaSID + '-' + '514',
                'displayName': 'Nobody',
                'acctFlags': '[NUD        ]'
            }
        }

        for user, property in users.iteritems():
            self.smb.createSambaUser(name=user, uid=property['uid'],
                                     gid=property['gid'],
                                     sambaSID=property['sambaSID'],
                                     sambaPrimaryGroupSID=property['sambaPrimaryGroupSID'],
                                     displayName=property['displayName'],
                                     gecos=property['displayName'],
                                     sambaAcctFlags=property['acctFlags'])
            # ask for root password
            if property['uid'] == '0':
                password = getpass.getpass('Password for root: ')
                self.smb.changeUserPassword(user, password, 0)

    def createSambaGroups(self):
        suffix       = self.cfg.getOp('samba', 'ldap suffix')
        group_suffix = self.cfg.getOp('samba', 'ldap group suffix')
        sid          = self.cfg.getOp('samba', 'sambaSID')

        suffix = group_suffix + ',' + suffix

        # default Samba domain groups
        groups = {
            'Domain Admins':    {
                'description': 'Domain Administrators',
                'gidNumber': '512',
                'sambaGroupType': '2',
                'sambaSID': sid + '-512'
            },
            'Domain Users': {
                'description': 'Domain Users',
                'gidNumber': '513',
                'sambaGroupType': '2',
                'sambaSID': sid + '-513'
            },
            'Domain Guests':    {
                'description': 'Domain Guests',
                'gidNumber': '514',
                'sambaGroupType': '2',
                'sambaSID': sid + '-514'
            },
            'Domain Computers': {
                'description': 'Domain Computers accounts',
                'gidNumber': '515',
                'sambaGroupType': '2',
                'sambaSID': sid + '-515'
            },
            'Administrators':   {
                'description': 'Administrators',
                'gidNumber': '544',
                'sambaGroupType': '5',
                'sambaSID': 'S-1-5-32-544'
            },
            'Account Operators':    {
                'description': 'Domain Users to manipulate users accounts',
                'gidNumber': '544',
                'sambaGroupType': '5',
                'sambaSID': 'S-1-5-32-548'
            },
            'Print Operators':  {
                'description': 'Domain Print Operators',
                'gidNumber': '550',
                'sambaGroupType': '5',
                'sambaSID': 'S-1-5-32-550'
            },
            'Backup Operators': {
                'description': 'Domain Backup Operators',
                'gidNumber': '551',
                'sambaGroupType': '5',
                'sambaSID': 'S-1-5-32-551'
            },
            'Replicators':  {
                'description': 'Domain Supports file replication in a sambaDomainName',
                'gidNumber': '552',
                'sambaGroupType': '5',
                'sambaSID': 'S-1-5-32-552'
            }
        }

        # create Samba domain groups
        for groupName, property in groups.iteritems():
            self.smb.createSambaGroup(groupName,
                                      gid=property['gidNumber'],
                                      sambaSID=property['sambaSID'],
                                      description=property['description'],
                                      sambaGroupType=property['sambaGroupType']
                                      )

    def createRootDN(self):
        dn = self.cfg.getOp('samba', 'ldap suffix')
        dc = re.match('^dc=([^,.]*)', dn)

        if dc:
            organization = dc.groups()[0]
        else:
            organization = "SetMe"

        attrs = [
            ('objectClass', ['top', 'dcObject', 'organization'] ),
            ('dc', [organization] ),
            ('o', [organization] )
        ]

        try:
            self.smb.ldap_add(dn, attrs)
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.LDAPError, e:
            print dn + ': ', e.args

    def createContainers(self):
        suffix   = self.cfg.getOp('samba', 'ldap suffix')
        users    = self.cfg.getOp('samba', 'ldap user suffix')
        groups   = self.cfg.getOp('samba', 'ldap group suffix')
        machines = self.cfg.getOp('samba', 'ldap machine suffix')

        for container in [users, groups, machines]:
            self.createContainerObject(container + ',' + suffix)

    def createContainerObject(self, dn):
        dc    = re.match('^dc=([^,.]*),', dn)
        ou    = re.match('^ou=([^,.]*),', dn)
        attrs = []

        if dc: # container is of type domain component
            dcname = dc.groups()[0]
            attrs  = [
                ('objectClass', ['top', 'dcObject', 'namedObject']),
                ('dc', [dcname])
            ]

        if ou: # container is of type organizational unit
            ouname = ou.groups()[0]
            attrs  = [
                ('objectClass', ['top', 'organizationalUnit']),
                ('ou', [ouname])
            ]

        try:
            self.smb.ldap_add(dn, attrs)
            print dn + ': Successfully created'
        except ldap.ALREADY_EXISTS, e:
            print dn + ': Already exists'
        except ldap.LDAPError, e:
            print dn + ': ', e.args

def do_population(argv):
    p = Population(cfgfile)
    p.createRootDN()
    p.createSambaDomain()
    p.createContainers()
    p.createSambaGroups()
    p.createSambaUsers()

def manage_user(argv):
    usage = '%prog user [-h | --help] | <name> [Options]'
    parser = optparse.OptionParser(usage)
    parser.add_option("-a", "--add", dest='add', help='add new user <name>')
    parser.add_option("-d", "--delete", dest='delete', help='delete existing user <name>')
    parser.add_option("-m", "--modify", dest='modify', help='modify properties of user <name>')
    parser.add_option("-R", "--remove", dest='remove', help='remove a user property (with --modify)', action='store_true')
    parser.add_option("-u", "--uidNumber", dest='uidNumber', help='create new user with uidNumber')
    parser.add_option("-g", "--gidNumber", dest='gidNumber', help='create new user with gidNumber')
    parser.add_option("-G", "--groupName", dest='groupName', help='add user to group (-R remove user from group)', action='append')
    parser.add_option("-W", "--askPassword", dest='askPassword', help='prompt for users password', action='store_true')
    parser.add_option("-H", "--home", dest='home', help='home directory')
    parser.add_option("-k", "--skeleton", dest='skeleton', help='skeleton directory (with -M)')
    parser.add_option("-s", "--loginShell", dest='loginShell', help='login shell')
    parser.add_option("-I", "--aixAccount", dest='aixAccount', help='create AIX account instead of Posix account')
    parser.add_option("-S", "--sambaAccount", dest='sambaAccount', help='is a Samba user (otherwise Posix only)', action='store_true')
    parser.add_option("-n", "--givenName", dest='givenName', help='firstname of the user')
    parser.add_option("-N", "--sn", dest='sn', help='surname of the user')
    parser.add_option("-M", "--mail", dest='mail', help='emailaddress')
    parser.add_option("-C", "--sambaHomePath", dest='sambaHomePath', help='Samba home share')
    parser.add_option("-D", "--sambaHomeDrive", dest='sambaHomeDrive', help='Windows home drive letter (H:)')
    parser.add_option("-F", "--sambaProfilePath", dest='sambaProfilePath', help='profile directory (\\\\PDC\\profiles\\user)')
    parser.add_option("-E", "--sambaLogonScript", dest='sambaLogonScript', help='DOS script to execute on login')
    parser.add_option("-A", "--canChangePassword", dest='canChangePassword', help='days after which user is allowed to change password (with --askPassword)')
    parser.add_option("-B", "--mustChangePassword", dest='mustChangePassword', help='days after which user must change password (with --askPassword)')
    parser.add_option("-X", "--accountDisabled", dest='accountDisabled', help='user account is disabled', action='store_true')
    parser.add_option("-Y", "--accountEnabled", dest='accountDisabled', help='user account is disabled', action='store_false')

    (options, args) = parser.parse_args(argv)
    
    if options.add and options.delete:
        parser.error('options -a and -d are mutually exclusive')
    if options.add and options.modify:
        parser.error('options -a and -m are mutually exclusive')
    if options.delete and options.modify:
        parser.error('options -d and -m are mutually exclusive')
    if not options.add and not options.delete and not options.modify:
        parser.error('Please specify an action! Use option --help')

    acc = Account(cfgfile)

    if options.add:
        uid = None; gid = None; sambaAcctFlags=None

        if options.uidNumber:
            uid = options.uidNumber
        if options.gidNumber:
            gid = options.gidNumber
        if options.accountDisabled:
            sambaAcctFlags = '[UD         ]'
        else:
            sambaAcctFlags = '[U          ]'


        if options.sambaAccount:
            acc.createSambaUser(options.add, uid=uid, gid=gid, 
                                    loginShell=options.loginShell,
                                    givenName=options.givenName,
                                    sn=options.sn,
                                    mail=options.mail,
                                    sambaHomePath=options.sambaHomePath,
                                    sambaHomeDrive=options.sambaHomeDrive,
                                    sambaProfilePath=options.sambaProfilePath,
                                    sambaLogonScript=options.sambaLogonScript,
                                    sambaAcctFlags=sambaAcctFlags)
        else:
            acc.createPosixUser(name=options.add, uid=uid, gid=gid,
                                  loginShell=options.loginShell)

        uid = acc.getUserUid(options.add)
        gid = acc.getUserGid(options.add)

        if options.groupName:
            for id, groupname in enumerate(options.groupName):
                acc.addUserToGroup(options.add, groupname)
        if options.askPassword:
            password = getpass.getpass('Password for ' + options.add + ': ')
            acc.changeUserPassword(options.add, password,
                                     options.canChangePassword,
                                     options.mustChangePassword)

    if options.delete:
        acc.deleteUser(options.delete)

    if options.modify:
        if options.groupName:
            for groupname in options.groupName:
                if options.remove:
                    acc.deleteUserFromGroup(options.modify, groupname)
                else:
                    acc.addUserToGroup(options.modify, groupname)

        if options.uidNumber:
            acc.modifyUser(options.modify, 'uidNumber', options.uidNumber)
        if options.gidNumber:
            acc.modifyUser(options.modify, 'gidNumber', options.gidNumber)
        if options.askPassword:
            password = getpass.getpass('Password for ' + options.modify + ': ')
            acc.changeUserPassword(options.modify, password,
                                     options.canChangePassword,
                                     options.mustChangePassword)
        if options.home:
            acc.modifyUser(options.modify, 'homeDirectory', options.home)
        if options.loginShell:
            acc.modifyUser(options.modify, 'loginShell', options.loginShell)
        if options.givenName:
            acc.modifyUser(options.modify, 'givenName', options.givenName)
        if options.sn:
            acc.modifyUser(options.modify, 'sn', options.sn)
        if options.sambaHomePath:
            acc.modifyUser(options.modify, 'sambaHomePath', options.sambaHomePath)
        if options.sambaHomeDrive:
            acc.modifyUser(options.modify, 'sambaHomeDrive', options.sambaHomeDrive)
        if options.sambaProfilePath:
            acc.modifyUser(options.modify, 'sambaProfilePath', options.sambaProfilePath)
        if options.sambaLogonScript:
            acc.modifyUser(options.modify, 'sambaLogonScript', options.sambaLogonScript)
        if options.accountDisabled == True:
            acc.modifyUser(options.modify, 'sambaAcctFlags', '[UD         ]')
        if options.accountDisabled == False:
            acc.modifyUser(options.modify, 'sambaAcctFlags', '[U         ]')

def manage_group(argv):
    usage = '%prog group [-h | --help] | -n <name> [Options]'
    parser = optparse.OptionParser(usage)
    parser.add_option("-a", "--add", dest='add', help='add new group <name>')
    parser.add_option("-d", "--delete", dest='delete', help='delete existing group <name>')
    parser.add_option("-m", "--modify", dest='modify', help='modify existing group <name>')
    parser.add_option("-g", "--gidNumber", dest='gidNumber', help='create new group with this gid')
    parser.add_option("-S", "--sambaGroup", dest='sambaGroup', help='create Samba group otherwise Posix group is created', action='store_true')
    parser.add_option("-s", "--sambaSid", dest='sambaSID', help='group sambaSID')
    parser.add_option("-t", "--type", dest='groupType', help='Samba group type')
    parser.add_option("-N", "--displayName", dest='displayName', help='Windows full display name')
    parser.add_option("-c", "--description", dest='description', help='group description')

    (options, args) = parser.parse_args(argv)

    if options.add and options.delete:
        parser.error('options -a and -d are mutually exclusive')
    if options.add and options.modify:
        parser.error('options -a and -m are mutually exclusive')
    if options.delete and options.modify:
        parser.error('options -d and -m are mutually exclusive')
    if not options.add and not options.delete and not options.modify:
        parser.error('Please specify an action! Use option --help')

    acc = Account(cfgfile)

    # add new group
    if options.add:
	if options.sambaGroup:
            acc.createSambaGroup(options.add, options.gidNumber,
                               options.sambaSID, options.description,
                               options.groupType)
        else:
            acc.createPosixGroup(options.add, options.gidNumber,
                               options.description)
	
    # delete existing group
    if options.delete:
        acc.deleteGroup(options.delete)

    # modify existing group
    if options.modify:
        if options.gidNumber:
            acc.modifyGroup(options.modify, 'gidNumber', options.gidNumber)
        if options.sambaSID:
            acc.modifyGroup(options.modify, 'sambaSID', options.sambaSID)
        if options.groupType:
            acc.modifyGroup(options.modify, 'sambaGroupType', options.groupType)
        if options.displayName:
            acc.modifyGroup(options.modify, 'displayName', options.displayName)
        if options.description:
            acc.modifyGroup(options.modify, 'description', options.description)

def manage_machine(argv):
    usage = '%prog machine [-h | --help] | -n <name> [Options]'
    parser = optparse.OptionParser(usage)
    parser.add_option("-a", "--add", dest='add', help='add new machine', action='store_true')
    parser.add_option("-d", "--delete", dest='delete', help='delete existing machine', action='store_true')
    parser.add_option("-m", "--modify", dest='modify', help='modify existing machine', action='store_true')
    parser.add_option("-n", "--name", dest='name', help='name of the machine')
    parser.add_option("-u", "--uidNumber", dest='uidNumber', help='create new machine with this uid')
    parser.add_option("-g", "--gidNumber", dest='gidNumber', help='create new machine with this gid')
    parser.add_option("-S", "--sambaAccount", dest='sambaAccount', help='is a Samba machine (otherwise Posix only)', action='store_true')
    parser.add_option("-N", "--displayName", dest='displayName', help='Windows full display name')
    parser.add_option("-s", "--sambaSid", dest='sambaSID', help='machine sambaSID')

    (options, args) = parser.parse_args(argv)

    if options.add and options.delete:
        parser.error('options -a and -d are mutually exclusive')
    if options.add and options.modify:
        parser.error('options -a and -m are mutually exclusive')
    if options.delete and options.modify:
        parser.error('options -d and -m are mutually exclusive')
    if not options.name:
        parser.error('Name is missing! Use option --help')
    if not options.add and not options.delete and not options.modify:
        parser.error('Please specify an action! Use option --help')

    acc = Account(cfgfile)

    # add new machine
    if options.add:
        if options.sambaAccount:
            acc.createSambaMachine(options.name, options.uidNumber,
                                     options.gidNumber, options.displayName,
                                     options.sambaSID)
        else:
            acc.createPosixMachine(options.name, options.uidNumber,
                                     options.gidNumber, options.displayName)

    # delete existing machine
    if options.delete:
        acc.deleteMachine(options.name)

    # modify existing machine
    if options.modify:
        if options.uidNumber:
            acc.modifyMachine(options.name, 'uidNumber', options.uidNumber)
        if options.gidNumber:
            acc.modifyMachine(options.name, 'gidNumber', options.gidNumber)
        if options.displayName:
            acc.modifyMachine(options.name, 'displayName', options.displayName)
        if options.sambaSID:
            acc.modifyMachine(options.name, 'sambaSID', options.sambaSID)

def usage(argv):
    cmd = argv[0]
    print 'Usage: ' + cmd + ' [populate | user | group | machine]'
    exit(1)

def main():
    args = sys.argv
    if len(args) < 2:
        usage(args)

    command  = args[1]
    commands = { 'populate': do_population,
                 'user'    : manage_user,
                 'group'   : manage_group,
                 'machine' : manage_machine }

    try:
        commands[command.lower()](args)
    except KeyError, e:
        print 'Unknown action: ', e
        usage(args)

if __name__ == '__main__':
    main()
