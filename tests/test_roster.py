import copy
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'skills/server-testflight/scripts/sync_internal_testers.py'
spec=importlib.util.spec_from_file_location('roster',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Fake:
    def __init__(self, user=True, roles=None, pending=False, installed=False):
        self.writes=[]
        self.users=[{'id':'u','attributes':{'username':'tester@example.org','roles':roles or ['CUSTOMER_SUPPORT','FINANCE'],'allAppsVisible':True}}] if user else []
        self.pending=[{'id':'i','attributes':{'email':'tester@example.org'}}] if pending else []
        self.testers=[{'id':'t','attributes':{'email':'tester@example.org','state':'INSTALLED'}}] if installed else []
    def all(self,path):
        if path.startswith('/v1/users?'):return copy.deepcopy(self.users)
        if path.startswith('/v1/userInvitations?'):return copy.deepcopy(self.pending)
        if '/betaTesters?' in path:return copy.deepcopy(self.testers)
        raise AssertionError(path)
    def api(self,method,path,body=None):
        if method=='GET':
            if path=='/v1/apps/a':return {'data':{'attributes':{'bundleId':'org.example.app'}}}
            if path.startswith('/v1/betaGroups/g?'):return {'data':{'attributes':{'isInternalGroup':True,'hasAccessToAllBuilds':True},'relationships':{'app':{'data':{'id':'a'}}}}}
            raise AssertionError(path)
        self.writes.append((method,path,body))
        if path=='/v1/users/u':self.users[0]['attributes']['roles']=body['data']['attributes']['roles'];return {}
        if path=='/v1/betaTesters':
            t={'id':'t','attributes':{'email':body['data']['attributes']['email'],'state':'INVITED'}};self.testers.append(t);return {'data':t}
        if path=='/v1/userInvitations':
            i={'id':'i','attributes':body['data']['attributes']};self.pending.append(i);return {'data':i}
        raise AssertionError(path)

class RosterTests(unittest.TestCase):
    config={'app_id':'a','group_id':'g','bundle_id':'org.example.app'}
    def test_preserve_existing_roles_and_do_not_repeat_writes(self):
        fake=Fake();entry={'email':'tester@example.org','allow_add_marketing':True}
        result=module.reconcile(fake,self.config,[entry])
        self.assertTrue(result[0]['member'])
        self.assertEqual(fake.users[0]['attributes']['roles'],['CUSTOMER_SUPPORT','FINANCE','MARKETING'])
        count=len(fake.writes);module.reconcile(fake,self.config,[entry]);self.assertEqual(len(fake.writes),count)
    def test_unknown_user_is_invited_only_once_and_only_to_intended_app(self):
        fake=Fake(user=False);entry={'email':'tester@example.org','first_name':'Demo','last_name':'Tester','allow_team_invitation':True}
        a=module.reconcile(fake,self.config,[entry]);b=module.reconcile(fake,self.config,[entry])
        self.assertEqual(a[0]['state'],'TEAM_INVITATION_PENDING');self.assertEqual(b[0]['state'],'TEAM_INVITATION_PENDING')
        self.assertEqual(len(fake.writes),1)
        body=fake.writes[0][2]['data'];self.assertFalse(body['attributes']['allAppsVisible']);self.assertFalse(body['attributes']['provisioningAllowed']);self.assertEqual(body['attributes']['roles'],['MARKETING'])
        self.assertEqual(body['relationships']['visibleApps']['data'],[{'type':'apps','id':'a'}])
    def test_no_role_change_without_explicit_authorization(self):
        fake=Fake();result=module.reconcile(fake,self.config,[{'email':'tester@example.org'}])
        self.assertEqual(result[0]['state'],'ROLE_AUTHORIZATION_REQUIRED');self.assertEqual(fake.writes,[])
    def test_installed_user_is_not_reinvited(self):
        fake=Fake(roles=['ADMIN'],installed=True);result=module.reconcile(fake,self.config,[{'email':'tester@example.org'}],send_invites=True)
        self.assertEqual(result[0]['state'],'INSTALLED');self.assertEqual(fake.writes,[])

if __name__=='__main__':unittest.main()

class ManageTests(unittest.TestCase):
    def test_remove_then_readd_clears_exclusion(self):
        path=Path(__file__).resolve().parents[1]/'skills/server-testflight/scripts/manage_roster.py'
        s=importlib.util.spec_from_file_location('manage',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
        data=[{'email':'tester@example.org','allow_app_access':True}]
        removed=m.edit(data,'remove','tester@example.org')
        self.assertEqual(removed['testers'],[]);self.assertEqual(removed['removed'],['tester@example.org'])
        added=m.edit(removed,'add','tester@example.org')
        self.assertEqual(added['removed'],[]);self.assertEqual(len(added['testers']),1)
