'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

const roles = [
  ['seeker','Job Seeker','Browse, save and apply'],['fresher','Student / Fresher','Start your career'],['professional','Working Professional','Grow and switch'],
  ['recruiter','Recruiter / Hiring Manager','Find the right talent'],['employer','Company / Employer','Manage jobs and talent'],['admin','Admin / Platform Ops','Operate the platform']
];
export default function Home(){
 const [health,setHealth]=useState('checking');
 useEffect(()=>{fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL||'http://localhost:8080'}/api/v1/public/status`).then(r=>r.ok?r.json():Promise.reject()).then(()=>setHealth('online')).catch(()=>setHealth('offline'))},[]);
 return <main>
  <header className="top"><div className="wrap nav"><Link className="brand" href="/">Job<span>Hub</span></Link><nav><a href="#jobs">Jobs</a><a href="#companies">Companies</a><a href="#industries">Industries</a><a href="#insights">Career Insights</a><a href="/reference/jobhub_portal.html">UI Reference</a></nav><div className="actions"><Link className="btn secondary" href="/login">Sign in</Link></div></div></header>
  <section className="hero"><div className="wrap heroGrid"><div><div className="eyebrow">✦ AI-powered job intelligence</div><h1>Find Your Next <span>Opportunity</span></h1><p>Jobs from multiple sources, career intelligence and role-based workspaces—built on the JobHub architecture.</p><div className="search"><input placeholder="Job title, skills or keywords"/><input placeholder="Location e.g. Dubai"/><Link className="btn primary" href="/login">Search Jobs</Link></div><div className="trust"><div><b>250K+</b><span>Jobs indexed</span></div><div><b>10K+</b><span>Companies</span></div><div><b>50+</b><span>Countries</span></div><div><b>{health==='online'?'API Ready':'API Offline'}</b><span>Platform status</span></div></div></div><div className="heroArt"><div className="float one">95% Match<br/><small>Senior Java Developer</small></div><div className="float two">✓ Skills aligned<br/><b>4 new opportunities</b></div><div className="person"></div></div></div></section>
  <section className="section" id="jobs"><div className="wrap"><div className="head"><div><h2>Choose your JobHub experience</h2><p>Every persona gets the right navigation and access boundary.</p></div></div><div className="roles">{roles.map(([id,name,desc],i)=><Link key={id} href={`/login?role=${id}`} className="role"><div className="num">{i+1}. {name}</div><h3>{desc}</h3><p>Open role workspace →</p></Link>)}</div></div></section>
  <section className="section pale"><div className="wrap grid3"><div className="card"><b>Phase 0</b><h3>Foundation</h3><p>Docker, PostgreSQL, Flyway, Spring Boot, Next.js, CI and Codex rules.</p></div><div className="card"><b>Phase 1</b><h3>Identity + RBAC</h3><p>Tenants, users, roles, permissions, JWT and backend-enforced access control.</p></div><div className="card"><b>Data flow</b><h3>Audit + Outbox</h3><p>Every login creates auditable platform activity and an outbox event transactionally.</p></div></div></section>
  <footer className="footer"><div className="wrap foot"><div><div className="brand light">Job<span>Hub</span></div><p>Jobs. Skills. Growth. All in one place.</p></div><div><b>Developer</b><a href="/reference/jobhub_portal.html">Reference UI</a><Link href="/login">Demo login</Link></div></div></footer>
 </main>
}
