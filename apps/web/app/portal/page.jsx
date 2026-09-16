'use client';
import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';

const menus = {
  JOB_SEEKER: ['Dashboard', 'Job Search', 'Saved Jobs', 'My Applications', 'Profile'],
  STUDENT: ['Dashboard', 'Job Search', 'Internships', 'Learning Path', 'Resume'],
  PROFESSIONAL: ['Dashboard', 'Job Search', 'Target Roles', 'Applications', 'Resume & Profile'],
  RECRUITER: ['Dashboard', 'Candidate Search', 'Job Requisitions', 'Shortlists', 'Reports'],
  EMPLOYER: ['Overview', 'Jobs', 'Candidates', 'Talent Pipeline', 'Analytics'],
  ADMIN: ['Dashboard', 'Ingestion Monitor', 'Sweep Status', 'Jobs & Data Quality', 'Users', 'Audit Logs']
};

export default function Portal() {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [tab, setTab] = useState('');
  const [sweep, setSweep] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [jobCount, setJobCount] = useState(0);

  useEffect(() => {
    const t = localStorage.getItem('jobhub.accessToken');
    if (!t) { router.replace('/login'); return; }
    fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${t}` } })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setUser)
      .catch(() => { localStorage.clear(); router.replace('/login'); });
  }, []);

  useEffect(() => {
    if (user?.roles?.includes('ADMIN')) {
      fetch('/api/v1/admin/sweep/status')
        .then(r => r.json())
        .catch(() => ({}))
        .then(setSweep);
    }
  }, [user]);

  useEffect(() => {
    fetch('/api/v1/jobs/search?page=0&size=5')
      .then(r => r.json())
      .then(data => { setJobs(data.jobs || []); setJobCount(data.total || 0); })
      .catch(() => {});
  }, []);

  if (!user) return <div className="loading">Loading JobHub…</div>;

  const primary = user.roles?.[0] || 'JOB_SEEKER';
  const items = menus[primary] || menus.JOB_SEEKER;

  const renderContent = () => {
    switch (tab) {
      case 'Ingestion Monitor':
        return (
          <div className="card pad">
            <h2>Ingestion Monitor</h2>
            <div className="stats">
              <div className="card"><small>Total Raw Jobs</small><b>{jobCount.toLocaleString()}</b></div>
              <div className="card"><small>Sources Active</small><b>{sweep?.sources ? Object.keys(sweep.sources).length : 0}</b></div>
              <div className="card"><small>Last Sweep</small><b>{sweep?.lastSweep ? new Date(sweep.lastSweep).toLocaleString() : 'Pending'}</b></div>
            </div>
            <button className="btn primary" style={{ marginTop: 16 }} onClick={() => {
              fetch('/api/v1/admin/ingestion/run', { method: 'POST' })
                .then(r => r.json())
                .then(data => alert(data.status + ': ' + data.message));
            }}>Run Ingestion Now</button>
          </div>
        );
      case 'Sweep Status':
        return (
          <div className="card pad">
            <h2>Sweep Status</h2>
            {sweep?.sources && (
              <div style={{ display: 'grid', gap: 8 }}>
                {Object.entries(sweep.sources).map(([name, info]) => (
                  <div key={name} style={{ display: 'flex', justifyContent: 'space-between', padding: 8, background: 'var(--soft)', borderRadius: 6 }}>
                    <span>{name}</span>
                    <span>{info.jobs} jobs — {info.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      case 'Job Search':
        router.push('/jobs');
        return null;
      default:
        return (
          <div className="card pad">
            <h2>{tab || items[0]}</h2>
            <p>Authenticated workspace with backend-enforced role access.</p>
            {primary === 'ADMIN' && sweep?.sources && (
              <div style={{ marginTop: 16 }}>
                <h3>Source Status</h3>
                <div style={{ display: 'grid', gap: 8 }}>
                  {Object.entries(sweep.sources).map(([name, info]) => (
                    <div key={name} style={{ display: 'flex', justifyContent: 'space-between', padding: 8, background: 'var(--soft)', borderRadius: 6 }}>
                      <span>{name}</span>
                      <span>{info.jobs} jobs — {info.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
    }
  };

  return (
    <main className="portalPage">
      <aside className="side">
        <div className="brand light">Job<span>Hub</span></div>
        <div className="caption">{user.tenantKey}</div>
        {items.map(x => (
          <button key={x} className={tab === x ? 'active' : ''} onClick={() => setTab(x)}>{x}</button>
        ))}
        <div className="sideFoot">
          <button onClick={() => { localStorage.clear(); router.push('/'); }}>↪ Sign out</button>
        </div>
      </aside>
      <section className="portalMain">
        <header className="portalTop">
          <div><b>JobHub</b><span> / {tab || items[0]}</span></div>
          <div className="userPill">
            <span className="avatar">{user.displayName?.slice(0, 2).toUpperCase()}</span>
            <div><b>{user.displayName}</b><small>{primary}</small></div>
          </div>
        </header>
        <div className="portalContent">
          {renderContent()}
          {jobs.length > 0 && tab !== 'Ingestion Monitor' && tab !== 'Sweep Status' && (
            <div className="card pad" style={{ marginTop: 16 }}>
              <h3>Recent Jobs ({jobCount.toLocaleString()} total)</h3>
              {jobs.slice(0, 3).map(job => (
                <div key={job.id} style={{ padding: 8, borderBottom: '1px solid var(--line)' }}>
                  <b>{job.externalJobId}</b>
                  <small style={{ color: 'var(--muted)', marginLeft: 8 }}>{new Date(job.fetchedAt).toLocaleDateString()}</small>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
