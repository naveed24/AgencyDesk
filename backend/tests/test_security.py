"""Live PostgreSQL integration tests with FastAPI TestClient.
Run after setup: python -m pytest -v
These tests intentionally fail when the seed is missing; they do not silently skip.
"""
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.database import SessionLocal, settings
from app.main import app

SEED_PATH = Path(__file__).resolve().parents[1] / '.seed_ids.json'

@pytest.fixture(scope='module')
def scenario():
    if not SEED_PATH.is_file():
        pytest.fail('Run python seed_demo.py first (missing .seed_ids.json)')
    password = os.getenv('DEMO_PASSWORD', settings.demo_password)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        ids = json.loads(SEED_PATH.read_text())
        def auth(email,agency_id):
            r=client.post('/auth/login',json={'email':email,'password':password,'agency_id':agency_id})
            assert r.status_code==200, f'Login {email}: {r.status_code} {r.text}'
            return {'Authorization': 'Bearer '+r.json()['access_token']}
        ids['admin_headers']=auth('admin@agencydesk.local',ids['agency_a'])
        ids['client_headers']=auth('client@agencydesk.local',ids['agency_a'])
        ids['member_headers']=auth('member@agencydesk.local',ids['agency_a'])
        ids['blue_headers']=auth('blueadmin@agencydesk.local',ids['agency_b'])
        yield client, ids, password


def test_agencies_cannot_read_each_others_projects_or_tasks(scenario):
    c,s,_=scenario
    r=c.get('/projects',headers=s['admin_headers'])
    assert r.status_code==200
    assert all(p['agency_id']==s['agency_a'] for p in r.json())
    assert c.get(f"/projects/{s['project_blue']}",headers=s['admin_headers']).status_code==404
    assert c.get(f"/tasks/{s['task_blue']}",headers=s['admin_headers']).status_code==404
    assert c.get(f"/projects/{s['project_acme']}",headers=s['blue_headers']).status_code==404
    assert c.post('/projects',json={'name':'Cross tenant','client_id':s['client_blue']},headers=s['admin_headers']).status_code==404


def test_client_only_sees_own_projects_and_visible_tasks(scenario):
    c,s,_=scenario
    r=c.get('/projects',headers=s['client_headers']);assert r.status_code==200
    assert {p['id'] for p in r.json()}=={s['project_acme']}
    r=c.get(f"/projects/{s['project_acme']}/tasks",headers=s['client_headers'])
    assert r.status_code==200
    assert all(t['is_client_visible'] for t in r.json())
    assert s['task_visible'] in {t['id'] for t in r.json()}
    assert s['task_internal'] not in {t['id'] for t in r.json()}
    assert c.get(f"/tasks/{s['task_internal']}",headers=s['client_headers']).status_code==404
    assert c.get(f"/projects/{s['project_private']}/tasks",headers=s['client_headers']).status_code==404
    assert c.post(f"/projects/{s['project_acme']}/tasks",headers=s['client_headers'],json={'title':'Forbidden'}).status_code==403
    assert c.patch(f"/tasks/{s['task_visible']}",headers=s['client_headers'],json={'status':'done'}).status_code==403


def test_assigned_members_cannot_see_unassigned_projects(scenario):
    c,s,_=scenario
    r=c.get('/projects',headers=s['member_headers']);assert r.status_code==200
    assert {p['id'] for p in r.json()}=={s['project_acme']}
    assert c.get(f"/projects/{s['project_private']}",headers=s['member_headers']).status_code==404


def test_internal_comments_are_hidden(scenario):
    c,s,_=scenario
    r=c.get(f"/tasks/{s['task_visible']}/comments",headers=s['client_headers']);assert r.status_code==200
    comments=r.json()
    assert comments and all(row['is_client_visible'] for row in comments)
    assert not any('budget' in row['content'].lower() for row in comments)
    assert c.get(f"/tasks/{s['task_internal']}/comments",headers=s['client_headers']).status_code==404


def test_internal_files_unavailable_even_by_known_id(scenario):
    c,s,_=scenario
    r=c.get(f"/tasks/{s['task_visible']}/files",headers=s['client_headers']);assert r.status_code==200
    assert s['file_visible'] in {f['id'] for f in r.json()}
    assert s['file_internal'] not in {f['id'] for f in r.json()}
    assert c.get(f"/files/{s['file_visible']}/download",headers=s['client_headers']).status_code==200
    assert c.get(f"/files/{s['file_internal']}/download",headers=s['client_headers']).status_code==404
    assert c.get(f"/files/{s['file_visible']}/download",headers=s['blue_headers']).status_code==404
    r=c.patch(f"/files/{s['file_visible']}/review",json={'status':'approved'},headers=s['client_headers']);assert r.status_code==200
    assert r.json()['approval_status']=='approved'
    assert c.patch(f"/files/{s['file_internal']}/review",json={'status':'approved'},headers=s['client_headers']).status_code==404


def test_client_dashboard_scopes_hours_and_counts(scenario):
    c,s,_=scenario
    client=c.get(f"/projects/{s['project_acme']}/dashboard",headers=s['client_headers'])
    admin=c.get(f"/projects/{s['project_acme']}/dashboard",headers=s['admin_headers'])
    assert client.status_code==admin.status_code==200
    assert client.json()['total_tasks'] < admin.json()['total_tasks']
    assert client.json()['total_minutes'] < admin.json()['total_minutes']
    assert c.post(f"/tasks/{s['task_visible']}/time-entries",json={'duration_minutes':25},headers=s['client_headers']).status_code==403


def test_invite_resend_and_idempotent_accept(scenario):
    c,s,password=scenario
    email=f'takehome-{uuid4().hex[:10]}@agencydesk.local'
    req={'email':email,'role':'agency_member'}
    first=c.post('/invitations',headers=s['admin_headers'],json=req)
    second=c.post('/invitations',headers=s['admin_headers'],json=req)
    assert first.status_code==second.status_code==201, (first.text,second.text)
    assert first.json()['id']==second.json()['id']
    with SessionLocal() as db:
        count=db.execute(text("""
            SELECT COUNT(*) FROM public.invitations
            WHERE agency_id=:agency_id AND lower(email)=:email AND status='pending'
        """),{'agency_id':s['agency_a'],'email':email}).scalar_one()
    assert count==1
    payload={'token':second.json()['invite_token'],'password':password,'name':'Invited Member'}
    accepted=c.post('/invitations/accept',json=payload)
    repeated=c.post('/invitations/accept',json=payload)
    assert accepted.status_code==repeated.status_code==200, (accepted.text,repeated.text)
    assert accepted.json()['already_accepted'] is False
    assert repeated.json()['already_accepted'] is True
    with SessionLocal() as db:
        memberships=db.execute(text("""
            SELECT COUNT(*) FROM public.agency_memberships m
            JOIN public.users u ON u.id=m.user_id
            WHERE u.email=:email AND m.agency_id=:agency_id
        """),{'email':email,'agency_id':s['agency_a']}).scalar_one()
    assert memberships==1


def test_remove_member_unassigns_tasks_atomically(scenario):
    c,s,_=scenario
    # Ensure user is assigned before removing, and restore afterward.
    add=c.post(f"/projects/{s['project_acme']}/members",headers=s['admin_headers'],json={'user_id':s['user_member']})
    assert add.status_code==201
    assign=c.patch(f"/tasks/{s['task_internal']}",headers=s['admin_headers'],json={'assignee_user_id':s['user_member']})
    assert assign.status_code==200
    removed=c.delete(f"/projects/{s['project_acme']}/members/{s['user_member']}",headers=s['admin_headers'])
    assert removed.status_code==200, removed.text
    assert removed.json()['unassigned_tasks']>=1
    task=c.get(f"/tasks/{s['task_internal']}",headers=s['admin_headers'])
    assert task.json()['assignee_user_id'] is None
    assert c.get(f"/projects/{s['project_acme']}",headers=s['member_headers']).status_code==404
    assert c.post(f"/projects/{s['project_acme']}/members",headers=s['admin_headers'],json={'user_id':s['user_member']}).status_code==201


def test_same_person_different_roles_across_agencies(scenario):
    c, s, password = scenario
    other = c.post('/auth/login', json={
        'email': 'admin@agencydesk.local', 'password': password,
        'agency_id': s['agency_b']
    })
    assert other.status_code == 200
    headers = {'Authorization': 'Bearer ' + other.json()['access_token']}
    who = c.get('/auth/me', headers=headers)
    assert who.status_code == 200
    assert who.json()['role'] == 'client_user'
    assert c.get('/projects', headers=headers).status_code == 200
    assert c.post('/projects', headers=headers, json={
        'client_id': s['client_blue'], 'name': 'Forbidden client create'
    }).status_code == 403


def test_anonymous_cannot_access_private_routes(scenario):
    c, s, _ = scenario
    assert c.get('/projects').status_code == 401
    assert c.get(f"/tasks/{s['task_visible']}").status_code == 401
    assert c.get(f"/files/{s['file_visible']}/download").status_code == 401


def test_schema_rejects_cross_tenant_parent_child_reference(scenario):
    # Foreign key (agency_id, client_id) must reference the SAME agency.
    _, s, _ = scenario
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("""
                INSERT INTO public.projects (agency_id, client_id, name)
                VALUES (:agency_id, :client_id, 'Illegal cross-tenant link')
            """), {'agency_id': s['agency_a'], 'client_id': s['client_blue']})
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text("""
                INSERT INTO public.tasks (agency_id, project_id, title)
                VALUES (:agency_id, :project_id, 'Illegal cross-tenant task')
            """), {'agency_id': s['agency_a'], 'project_id': s['project_blue']})
        db.rollback()


def test_database_rejects_unknown_role(scenario):
    _, s, _ = scenario
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("""
                INSERT INTO public.agency_memberships (agency_id, user_id, role)
                VALUES (:aid, :uid, 'super_admin')
            """), {'aid': s['agency_b'], 'uid': s['user_member']})
        db.rollback()
