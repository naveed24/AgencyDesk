"""Idempotent local demo data for two agencies. Run from backend directory."""
import json
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from pwdlib import PasswordHash
from app.database import SessionLocal, settings

BASE = Path(__file__).resolve().parent

def one(db, sql, params):
    return db.execute(text(sql), params).scalar_one()

def find_or_create(db, table, where, args, fields):
    value = db.execute(text(f"SELECT id FROM public.{table} WHERE {where} ORDER BY id LIMIT 1"), args).scalar_one_or_none()
    if value is not None:
        return value
    keys = ', '.join(fields)
    binds = ', '.join(':'+f for f in fields)
    return one(db, f'INSERT INTO public.{table} ({keys}) VALUES ({binds}) RETURNING id', args)

def main():
    password = settings.demo_password
    if len(password) < 8: raise ValueError('Set DEMO_PASSWORD to 8+ characters in backend/.env')
    hashed = PasswordHash.recommended().hash(password)
    with SessionLocal.begin() as db:
        north = find_or_create(db, 'agencies', 'name=:name', {'name':'Northstar Agency'}, ['name'])
        blue = find_or_create(db, 'agencies', 'name=:name', {'name':'Bluebird Agency'}, ['name'])
        people = {
            'admin':('admin@agencydesk.local','Demo Admin'),
            'client':('client@agencydesk.local','Demo Client'),
            'member':('member@agencydesk.local','Demo Member'),
            'blueadmin':('blueadmin@agencydesk.local','Bluebird Admin'),
        }
        users={}
        for key, (email,name) in people.items():
            users[key] = one(db, """
                INSERT INTO public.users (email,name,password_hash)
                VALUES (:email,:name,:hash)
                ON CONFLICT (email) DO UPDATE SET password_hash=EXCLUDED.password_hash,
                                                  name=EXCLUDED.name
                RETURNING id
            """, {'email':email,'name':name,'hash':hashed})
        for who,agency,role in [
            ('admin',north,'agency_admin'),('admin',blue,'client_user'),
            ('client',north,'client_user'),('member',north,'agency_member'),
            ('blueadmin',blue,'agency_admin')]:
            db.execute(text("""
                INSERT INTO public.agency_memberships (user_id,agency_id,role)
                VALUES (:user_id,:agency_id,:role)
                ON CONFLICT(user_id,agency_id) DO UPDATE SET role=EXCLUDED.role
            """), {'user_id':users[who],'agency_id':agency,'role':role})
        clients={}
        for key,agency,name in [('acme',north,'Acme Corp'),('private',north,'Private Corp'),('blue',blue,'Bluebird Client')]:
            clients[key]=find_or_create(db,'clients','agency_id=:agency_id AND name=:name',
                {'agency_id':agency,'name':name},['agency_id','name'])
        for who,agency,client in [('client',north,'acme'),('admin',blue,'blue')]:
            db.execute(text("""
                INSERT INTO public.client_memberships (agency_id,client_id,user_id)
                VALUES (:agency_id,:client_id,:user_id)
                ON CONFLICT (agency_id,client_id,user_id) DO NOTHING
            """),{'agency_id':agency,'client_id':clients[client],'user_id':users[who]})
        projects={}
        for key,agency,client,name in [('acme',north,'acme','Acme Website'),('private',north,'private','Private Campaign'),('blue',blue,'blue','Bluebird Website')]:
            projects[key]=find_or_create(db,'projects','agency_id=:agency_id AND client_id=:client_id AND name=:name',
                {'agency_id':agency,'client_id':clients[client],'name':name}, ['agency_id','client_id','name'])
        db.execute(text("""
            INSERT INTO public.project_members (agency_id,project_id,user_id)
            VALUES (:agency_id,:project_id,:user_id)
            ON CONFLICT (agency_id,project_id,user_id) DO NOTHING
        """),{'agency_id':north,'project_id':projects['acme'],'user_id':users['member']})
        tasks={}
        for key,agency,project,title,visible,assignee in [
            ('visible',north,'acme','Design homepage',True,None),
            ('internal',north,'acme','Internal budget planning',False,users['member']),
            ('private',north,'private','Private campaign creative',True,None),
            ('blue',blue,'blue','Bluebird design review',True,None),
            ('blue_internal',blue,'blue','Bluebird internal strategy',False,None)]:
            tasks[key]=find_or_create(db,'tasks','agency_id=:agency_id AND project_id=:project_id AND title=:title',
                {'agency_id':agency,'project_id':projects[project], 'title':title,
                 'is_client_visible':visible,'assignee_user_id':assignee},
                ['agency_id','project_id','title','is_client_visible','assignee_user_id'])
            db.execute(text('UPDATE public.tasks SET is_client_visible=:visible WHERE id=:id AND agency_id=:agency_id'),
                {'visible':visible,'id':tasks[key],'agency_id':agency})
        for task_key,content,visible in [
            ('visible','Homepage is ready for client review',True),
            ('visible','Internal budget discussion',False)]:
            tid=tasks[task_key]
            found=db.execute(text('SELECT id FROM public.comments WHERE task_id=:tid AND agency_id=:aid AND content=:content LIMIT 1'),{'tid':tid,'aid':north,'content':content}).scalar_one_or_none()
            if found is None:
                db.execute(text('INSERT INTO public.comments (agency_id,task_id,user_id,content,is_client_visible) VALUES (:aid,:tid,:uid,:content,:visible)'),
                    {'aid':north,'tid':tid,'uid':users['admin'],'content':content,'visible':visible})
        for key,minutes in [('visible',90),('internal',120)]:
            tid=tasks[key]
            exists=db.execute(text('SELECT id FROM public.time_entries WHERE task_id=:tid AND note=:note LIMIT 1'),{'tid':tid,'note':'Seeded sample work'}).scalar_one_or_none()
            if exists is None:
                db.execute(text('INSERT INTO public.time_entries (agency_id,task_id,user_id,duration_minutes,note) VALUES (:aid,:tid,:uid,:duration,:note)'),
                    {'aid':north,'tid':tid,'uid':users['admin'],'duration':minutes,'note':'Seeded sample work'})
        file_dir=BASE/'uploads'/str(north)
        file_dir.mkdir(parents=True,exist_ok=True)
        files={}
        for key,filename,content,visible in [('visible','homepage-review.txt','Client-facing design review',True),
                                               ('internal','internal-budget.txt','Confidential budget notes',False)]:
            tid=tasks['visible']
            existing=db.execute(text('SELECT id FROM public.task_files WHERE task_id=:tid AND original_filename=:filename LIMIT 1'),
                                {'tid':tid,'filename':filename}).scalar_one_or_none()
            if existing is None:
                storage=f'{north}/{uuid4().hex}'
                (BASE/'uploads'/storage).write_text(content,encoding='utf-8')
                existing=one(db,"""
                    INSERT INTO public.task_files (agency_id,task_id,uploaded_by_user_id,original_filename,storage_path,content_type,is_client_visible)
                    VALUES (:aid,:tid,:uid,:filename,:storage,:content_type,:visible) RETURNING id
                """,{'aid':north,'tid':tid,'uid':users['admin'],'filename':filename,
                       'storage':storage,'content_type':'text/plain','visible':visible})
            files[key]=existing
    ids={'agency_a':north,'agency_b':blue,'client_acme':clients['acme'],'client_blue':clients['blue'],
         'project_acme':projects['acme'],'project_private':projects['private'],'project_blue':projects['blue'],
         'task_visible':tasks['visible'],'task_internal':tasks['internal'],'task_blue':tasks['blue'],
         'file_visible':files['visible'],'file_internal':files['internal'],
         'user_member':users['member']}
    (BASE/'.seed_ids.json').write_text(json.dumps(ids,indent=2))
    print('Demo seed completed. IDs saved to backend/.seed_ids.json')
    print('Agency A:',north,'Agency B:',blue)
    print('Logins: admin@agencydesk.local, client@agencydesk.local, member@agencydesk.local, blueadmin@agencydesk.local')

if __name__=='__main__': main()
