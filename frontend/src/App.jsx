import React, { useEffect, useState } from 'react';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const STATUSES = ['todo', 'in_progress', 'review', 'done'];
const DISPLAY = {todo:'To do', in_progress:'In progress', review:'Review', done:'Done'};
const pretty = value => value?.replaceAll('_', ' ') || '—';

async function request(path, token, options={}) {
  const headers = {...options.headers};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API}${path}`, {...options, headers});
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const message = Array.isArray(data.detail) ? data.detail.map(e=>e.msg).join(', ') : (data.detail || `Request failed (${res.status})`);
    throw new Error(message);
  }
  if (options.download) return res.blob();
  return res.json();
}

function Login({onLogin}) {
  const [email,setEmail] = useState('admin@agencydesk.local');
  const [password,setPassword] = useState('');
  const [agencyId,setAgencyId] = useState('1');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  async function submit(e){
    e.preventDefault(); setBusy(true); setError('');
    try {
      const login = await request('/auth/login', null, {method:'POST', body:JSON.stringify({email,password,agency_id:Number(agencyId)})});
      const user = await request('/auth/me', login.access_token);
      onLogin(login.access_token, user);
    } catch(err) {setError(err.message);} finally {setBusy(false);}
  }
  return <div className="login-backdrop"><div className="login-panel">
    <div className="brand"><span className="brand-mark">A</span> AgencyDesk</div>
    <div className="eyebrow">MULTI-TENANT WORKSPACE</div>
    <h1>Welcome back.</h1><p className="muted">Sign in to your agency or client workspace.</p>
    <form onSubmit={submit} className="form-stack">
      <label>Email<input required type="email" value={email} onChange={e=>setEmail(e.target.value)}/></label>
      <label>Password<input required type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
      <label>Agency ID<input required type="number" min="1" value={agencyId} onChange={e=>setAgencyId(e.target.value)}/></label>
      {error && <div className="error">{error}</div>}
      <button className="button primary" disabled={busy}>{busy?'Signing in…':'Sign in →'}</button>
    </form>
    <p className="hint">Demo users: admin@agencydesk.local · client@agencydesk.local. Use your seed script password and the actual agency ID.</p>
  </div></div>;
}

function FormPanel({title, children, onClose}) {return <section className="form-panel"><header className="panel-heading"><h3>{title}</h3><button className="icon-btn" onClick={onClose}>×</button></header>{children}</section>}
function Empty({children}) {return <div className="empty">{children}</div>}

function App() {
  const [session,setSession] = useState(null);
  const [projects,setProjects] = useState([]);
  const [clients,setClients] = useState([]);
  const [selected,setSelected] = useState(null);
  const [tasks,setTasks] = useState([]);
  const [activeTask,setActiveTask] = useState(null);
  const [comments,setComments] = useState([]);
  const [files,setFiles] = useState([]);
  const [dashboard,setDashboard] = useState(null);
  const [members,setMembers] = useState([]);
  const [view,setView] = useState('board');
  const [form,setForm] = useState('');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [draft,setDraft] = useState({});
  const token = session?.token;
  const user = session?.user;
  const admin = user?.role === 'agency_admin';
  const client = user?.role === 'client_user';
  const staff = !!user && !client;

  function alertError(e){setError(e.message || String(e));}
  async function refreshProjects(t=token) {
    const [p,c] = await Promise.all([request('/projects',t),request('/clients',t)]);
    setProjects(p); setClients(c);
    return p;
  }
  async function refreshProject(projectId, t=token) {
    if (!projectId) return;
    const [taskRows,summary,memberRows] = await Promise.all([
      request(`/projects/${projectId}/tasks`,t),
      request(`/projects/${projectId}/dashboard`,t),
      (user?.role === 'client_user' ? Promise.resolve([]) : request(`/projects/${projectId}/members`,t)),
    ]);
    setTasks(taskRows);setDashboard(summary);setMembers(memberRows);
  }
  async function refreshTask(taskId, t=token) {
    if (!taskId) return;
    const [task,commentRows,fileRows] = await Promise.all([
      request(`/tasks/${taskId}`,t),
      request(`/tasks/${taskId}/comments`,t),
      request(`/tasks/${taskId}/files`,t)
    ]);
    setActiveTask(task);setComments(commentRows);setFiles(fileRows);
  }
  async function run(fn) {setBusy(true);setError('');setNotice('');try{await fn();}catch(e){alertError(e);}finally{setBusy(false);}}
  async function login(t,u) {
    setSession({token:t,user:u});setError('');
    try {const p=await refreshProjects(t);if(p.length) setSelected(p[0].id);}catch(e){alertError(e);}
  }
  useEffect(()=>{if(selected && token)refreshProject(selected).catch(alertError);},[selected,token]);
  useEffect(()=>{if(activeTask?.id && token)refreshTask(activeTask.id).catch(alertError);},[activeTask?.id,token]);
  function logout(){setSession(null);setSelected(null);setActiveTask(null);setProjects([]);setTasks([]);setError('');}
  function begin(name,defaults={}){setDraft(defaults);setForm(name);setError('');setNotice('');}
  function close(){setForm('');setError('');}
  async function createClient(e) {e.preventDefault();await run(async()=>{const row=await request('/clients',token,{method:'POST',body:JSON.stringify({name:draft.name})}); await refreshProjects(); setNotice(`Created client ${row.name}`);close();});}
  async function createProject(e) {e.preventDefault();await run(async()=>{const row=await request('/projects',token,{method:'POST',body:JSON.stringify({client_id:Number(draft.client_id),name:draft.name,description:draft.description || null,status:'active'})});await refreshProjects();setSelected(row.id);close();});}
  async function createTask(e) {e.preventDefault();await run(async()=>{await request(`/projects/${selected}/tasks`,token,{method:'POST',body:JSON.stringify({title:draft.title,description:draft.description || null,status:'todo',priority:draft.priority || 'medium',due_date:draft.due_date || null,is_client_visible:!!draft.visible,assignee_user_id:draft.assignee_user_id?Number(draft.assignee_user_id):null})});await refreshProject(selected);close();});}
  async function updateTask(fields){await run(async()=>{const row=await request(`/tasks/${activeTask.id}`,token,{method:'PATCH',body:JSON.stringify(fields)});setActiveTask(row);await refreshProject(selected);setNotice('Task updated');});}
  async function addComment(e){e.preventDefault();await run(async()=>{await request(`/tasks/${activeTask.id}/comments`,token,{method:'POST',body:JSON.stringify({content:draft.comment,is_client_visible:client?true:!!draft.commentVisible})});await refreshTask(activeTask.id);setDraft(d=>({...d,comment:''}));});}
  async function addTime(e){e.preventDefault();await run(async()=>{await request(`/tasks/${activeTask.id}/time-entries`,token,{method:'POST',body:JSON.stringify({duration_minutes:Number(draft.minutes),note:draft.note || null,entry_date:null})});await refreshProject(selected);setNotice('Time logged successfully');setDraft(d=>({...d,minutes:'',note:''}));});}
  async function upload(e){e.preventDefault();await run(async()=>{const file = e.currentTarget.elements.uploadfile.files[0];if(!file)throw new Error('Choose a file');const body = new FormData();body.append('file',file);body.append('is_client_visible',draft.visible?'true':'false');await request(`/tasks/${activeTask.id}/files`,token,{method:'POST',body});await refreshTask(activeTask.id);setNotice('File uploaded');});}
  async function review(fileId,status){await run(async()=>{await request(`/files/${fileId}/review`,token,{method:'PATCH',body:JSON.stringify({status})});await refreshTask(activeTask.id);setNotice(`Marked ${pretty(status)}`);});}
  async function download(item){await run(async()=>{const blob=await request(`/files/${item.id}/download`,token,{download:true});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=item.original_filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);});}
  async function invite(e){e.preventDefault();await run(async()=>{const result=await request('/invitations',token,{method:'POST',body:JSON.stringify({email:draft.email,role:draft.role,client_id:draft.role==='client_user'?Number(draft.client_id):null})});setNotice(`Invitation token (copy now): ${result.invite_token}`);close();});}
  async function removeMember(id){if(!window.confirm('Remove project member and unassign their tasks?'))return;await run(async()=>{await request(`/projects/${selected}/members/${id}`,token,{method:'DELETE'});await refreshProject(selected);setNotice('Member removed; assigned tasks unassigned');});}
  async function addMember(e){e.preventDefault();await run(async()=>{await request(`/projects/${selected}/members`,token,{method:'POST',body:JSON.stringify({user_id:Number(draft.user_id)})});await refreshProject(selected);close();});}

  if (!session) return <Login onLogin={login}/>;
  const project = projects.find(p=>p.id===selected);
  const taskRows = STATUSES.map(status=>({status,items:tasks.filter(t=>t.status===status)}));
  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">A</span> AgencyDesk</div>
      <div className="nav-caption">WORKSPACE</div>
      <div className="workspace"><div className="workspace-icon">{client?'C':'A'}</div><div><strong>Agency #{user.agency_id}</strong><small>{pretty(user.role)}</small></div></div>
      <div className="nav-caption">PROJECTS</div>
      <div className="project-links">{projects.map(p=><button key={p.id} className={'nav-item '+(selected===p.id?'selected':'')} onClick={()=>{setSelected(p.id);setActiveTask(null);setView('board');}}><span>▦</span>{p.name}</button>)}</div>
      {admin && <button className="text-button" onClick={()=>begin('project')}>+ New project</button>}
      <div className="sidebar-bottom"><div className="user-avatar">{user.email.slice(0,1).toUpperCase()}</div><div className="identity"><strong>{user.email}</strong><small>{pretty(user.role)}</small></div><button className="icon-btn" title="Log out" onClick={logout}>↪</button></div>
    </aside>
    <main className="main"><div className="topbar"><span>Workspace <b>/</b> {project?.name || 'Projects'}</span><div className="top-right"><span className="pill">{client?'Client portal':'Agency workspace'}</span><span className="avatar">{user.email[0].toUpperCase()}</span></div></div>
      <div className="content"><header className="page-header"><div><div className="eyebrow">{project?`PROJECT #${project.id}`:'YOUR WORKSPACE'}</div><h1>{project?.name || 'Welcome to AgencyDesk'}</h1><p className="muted">{project?.description || 'Manage clients, projects, and teamwork securely.'}</p></div><div className="header-actions">{admin && <button className="button secondary" onClick={()=>begin('client')}>+ Client</button>}{staff&&project&&<button className="button primary" onClick={()=>begin('task',{priority:'medium',visible:true})}>+ New task</button>}</div></header>
      {error&&<div className="error banner">{error}<button onClick={()=>setError('')}>×</button></div>}{notice&&<div className="notice banner">{notice}<button onClick={()=>setNotice('')}>×</button></div>}
      {project ? <>
        <div className="tabs">{[['board','Task board'],['dashboard','Overview'],['members','Team']].map(([id,label])=><button className={view===id?'active':''} key={id} onClick={()=>setView(id)}>{label}</button>)}</div>
        {view==='board'&&<div className="board">{taskRows.map(({status,items})=><section className="lane" key={status}><div className="lane-header"><strong>{DISPLAY[status]}</strong><span className="counter">{items.length}</span></div>{items.map(task=><button key={task.id} className={'task-card '+(activeTask?.id===task.id?'focus':'')} onClick={()=>{setActiveTask(task);setDraft({});}}><div className="task-title">{task.title}</div><div className="task-description">{task.description||'No description'}</div><div className="task-tags"><span className={'tag priority-'+task.priority}>{pretty(task.priority)}</span><span className="tag">{task.is_client_visible?'Client visible':'Internal'}</span></div><div className="task-footer"><span>#{task.id}</span><span>{task.due_date||'No due date'}</span></div></button>)}{items.length===0&&<div className="lane-empty">No tasks</div>}</section>)}</div>}
        {view==='dashboard'&&<><div className="stats"><div className="stat"><span>Total tasks</span><strong>{dashboard?.total_tasks??'—'}</strong></div><div className="stat"><span>Hours logged</span><strong>{dashboard?.total_hours??'—'}h</strong></div><div className="stat"><span>Tasks done</span><strong>{dashboard?.task_counts?.done??'—'}</strong></div><div className="stat"><span>In progress</span><strong>{dashboard?.task_counts?.in_progress??'—'}</strong></div></div><section className="simple-card"><h3>Status breakdown</h3>{STATUSES.map(s=><div className="meter-row" key={s}><span>{DISPLAY[s]}</span><div className="meter"><span style={{width:`${dashboard?.total_tasks?100*(dashboard.task_counts[s]||0)/dashboard.total_tasks:0}%`}}/></div><b>{dashboard?.task_counts?.[s]||0}</b></div>)}<p className="hint">Counts and hours are scoped to your agency membership and the tasks you are allowed to see.</p></section></>}
        {view==='members'&&<section className="simple-card"><div className="section-heading"><h3>Assigned team</h3>{admin&&<button className="button small secondary" onClick={()=>begin('member')}>Add member</button>}</div>{members.length?members.map(m=><div className="member-row" key={m.user_id}><div><strong>{m.name}</strong><div className="muted smaller">{m.email} · {pretty(m.role)}</div></div>{admin&&<button className="button small danger" onClick={()=>removeMember(m.user_id)}>Remove</button>}</div>):<Empty>No agency staff assigned yet.</Empty>}</section>}
      </>:<section className="simple-card"><Empty>No accessible projects yet. {admin?'Create a client, then a project to get started.':'Ask your agency administrator for access.'}</Empty></section>}
      </div>
    </main>
    {activeTask&&view==='board'&&<aside className="detail"><div className="detail-header"><span>TASK #{activeTask.id}</span><button className="icon-btn" onClick={()=>setActiveTask(null)}>×</button></div><h2>{activeTask.title}</h2><p className="muted">{activeTask.description||'No description'}</p>
      <div className="info-row"><span>Status</span>{staff?<select value={activeTask.status} disabled={busy} onChange={e=>updateTask({status:e.target.value})}>{STATUSES.map(s=><option value={s} key={s}>{DISPLAY[s]}</option>)}</select>:<b>{DISPLAY[activeTask.status]}</b>}</div>
      <div className="info-row"><span>Priority</span><b>{pretty(activeTask.priority)}</b></div><div className="info-row"><span>Visibility</span><b>{activeTask.is_client_visible?'Client-visible':'Internal'}</b></div><div className="info-row"><span>Due</span><b>{activeTask.due_date||'—'}</b></div>
      <div className="detail-section"><h3>Comments</h3>{comments.map(c=><div className="comment" key={c.id}><small>Member #{c.user_id} · {c.is_client_visible?'Shared':'Internal'}</small><p>{c.content}</p></div>)}{comments.length===0&&<p className="muted smaller">No comments yet.</p>}<form onSubmit={addComment} className="form-stack"><textarea required placeholder="Write a comment..." value={draft.comment||''} onChange={e=>setDraft({...draft,comment:e.target.value})}/>{staff&&<label className="check-row"><input type="checkbox" checked={!!draft.commentVisible} onChange={e=>setDraft({...draft,commentVisible:e.target.checked})}/> Client visible</label>}<button className="button secondary small" disabled={busy}>Post comment</button></form></div>
      <div className="detail-section"><h3>Attachments</h3>{files.map(f=><div className="file-row" key={f.id}><div className="file-name"><button className="linklike" onClick={()=>download(f)}>↓ {f.original_filename}</button><small>{pretty(f.approval_status)} · {f.is_client_visible?'shared':'internal'}</small></div>{client&&<div className="review-actions"><button onClick={()=>review(f.id,'approved')}>Approve</button><button onClick={()=>review(f.id,'needs_changes')}>Needs changes</button></div>}</div>)}{files.length===0&&<p className="muted smaller">No files yet.</p>}{staff&&<form className="form-stack" onSubmit={upload}><input type="file" name="uploadfile" required/><label className="check-row"><input type="checkbox" checked={!!draft.visible} onChange={e=>setDraft({...draft,visible:e.target.checked})}/> Client visible</label><button className="button small secondary" disabled={busy}>Upload file</button><small className="muted">PDF, images, documents, ZIP · 10 MB maximum</small></form>}</div>
      {staff&&<div className="detail-section"><h3>Log time</h3><form className="form-stack" onSubmit={addTime}><input required min="1" max="1440" type="number" placeholder="Minutes worked" value={draft.minutes||''} onChange={e=>setDraft({...draft,minutes:e.target.value})}/><input placeholder="Work note" value={draft.note||''} onChange={e=>setDraft({...draft,note:e.target.value})}/><button className="button small secondary" disabled={busy}>Save time entry</button></form></div>}
    </aside>}
    {form&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)close();}}><div className="modal">
      {form==='client'&&<FormPanel title="New client" onClose={close}><form className="form-stack" onSubmit={createClient}><label>Client name<input required maxLength="150" value={draft.name||''} onChange={e=>setDraft({...draft,name:e.target.value})}/></label><button disabled={busy} className="button primary">Create client</button></form></FormPanel>}
      {form==='project'&&<FormPanel title="New project" onClose={close}><form className="form-stack" onSubmit={createProject}><label>Client<select required value={draft.client_id||''} onChange={e=>setDraft({...draft,client_id:e.target.value})}><option value="">Select a client</option>{clients.map(c=><option value={c.id} key={c.id}>{c.name}</option>)}</select></label><label>Project name<input required maxLength="150" value={draft.name||''} onChange={e=>setDraft({...draft,name:e.target.value})}/></label><label>Description<textarea value={draft.description||''} onChange={e=>setDraft({...draft,description:e.target.value})}/></label><button disabled={busy} className="button primary">Create project</button></form></FormPanel>}
      {form==='task'&&<FormPanel title="New task" onClose={close}><form className="form-stack" onSubmit={createTask}><label>Title<input required maxLength="200" value={draft.title||''} onChange={e=>setDraft({...draft,title:e.target.value})}/></label><label>Description<textarea value={draft.description||''} onChange={e=>setDraft({...draft,description:e.target.value})}/></label><label>Priority<select value={draft.priority||'medium'} onChange={e=>setDraft({...draft,priority:e.target.value})}><option>low</option><option>medium</option><option>high</option><option>urgent</option></select></label><label>Assignee<select value={draft.assignee_user_id||''} onChange={e=>setDraft({...draft,assignee_user_id:e.target.value})}><option value="">Unassigned</option>{members.map(m=><option key={m.user_id} value={m.user_id}>{m.name}</option>)}</select></label><label>Due date<input type="date" value={draft.due_date||''} onChange={e=>setDraft({...draft,due_date:e.target.value})}/></label><label className="check-row"><input type="checkbox" checked={!!draft.visible} onChange={e=>setDraft({...draft,visible:e.target.checked})}/> Client visible</label><button disabled={busy} className="button primary">Create task</button></form></FormPanel>}
      {form==='member'&&<FormPanel title="Assign staff to project" onClose={close}><form className="form-stack" onSubmit={addMember}><label>User ID<input required type="number" min="1" value={draft.user_id||''} onChange={e=>setDraft({...draft,user_id:e.target.value})}/></label><p className="hint">The user must already be an agency_admin or agency_member in this agency.</p><button disabled={busy} className="button primary">Add member</button></form></FormPanel>}
    </div></div>}
  </div>
}

export default App;
