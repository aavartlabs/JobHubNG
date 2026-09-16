'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

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
  const [selectedJob, setSelectedJob] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

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
      fetch('/api/v1/admin/sweep/status').then(r => r.json()).then(setSweep).catch(() => {});
    }
  }, [user]);

  useEffect(() => {
    if (tab === 'Job Search') return;
    fetch('/api/v1/jobs/search?page=0&size=5')
      .then(r => r.json())
      .then(data => { setJobs(data.jobs || []); setJobCount(data.total || 0); })
      .catch(() => {});
  }, [tab]);

  if (!user) return <div className="loading">Loading JobHub…</div>;

  const primary = user.roles?.[0] || 'JOB_SEEKER';
  const items = menus[primary] || menus.JOB_SEEKER;

  const handleSearch = async (query, page = 0) => {
    const params = new URLSearchParams({ q: query, page: page.toString(), size: '20' });
    const res = await fetch(`/api/v1/jobs/search?${params}`);
    return res.json();
  };

  const JobSearchContent = () => (
    <div className="jobSearchContainer">
      <div className="searchHeader">
        <input
          className="searchInput"
          placeholder="Job title, skills, keywords..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          onKeyDown={async e => {
            if (e.key === 'Enter') {
              const data = await handleSearch(searchQuery);
              setJobs(data.jobs || []);
              setJobCount(data.total || 0);
            }
          }}
        />
        <button className="btn primary" onClick={async () => {
          const data = await handleSearch(searchQuery);
          setJobs(data.jobs || []);
          setJobCount(data.total || 0);
        }}>Search</button>
      </div>
      <p style={{ color: 'var(--muted)', margin: '12px 0' }}>{jobCount.toLocaleString()} jobs available</p>
      <div className="jobList">
        {jobs.map(job => (
          <div key={job.id} className="jobCard" onClick={() => setSelectedJob(job)}>
            <div className="jobCardHeader">
              <h3>{job.externalJobId || 'Job Listing'}</h3>
              <span className="jobDate">{new Date(job.fetchedAt).toLocaleDateString()}</span>
            </div>
            <div className="jobMeta">
              <span>Source: {job.sourceId}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const JobDetailModal = ({ job, onClose }) => (
    <div className="modalOverlay" onClick={onClose}>
      <div className="modalContent" onClick={e => e.stopPropagation()}>
        <div className="modalHeader">
          <h2>{job.externalJobId || 'Job Details'}</h2>
          <button className="closeBtn" onClick={onClose}>×</button>
        </div>
        <div className="modalBody">
          <div className="detailRow"><label>ID:</label><span>{job.id}</span></div>
          <div className="detailRow"><label>External ID:</label><span>{job.externalJobId}</span></div>
          <div className="detailRow"><label>Source:</label><span>{job.sourceId}</span></div>
          <div className="detailRow"><label>Fetched:</label><span>{new Date(job.fetchedAt).toLocaleString()}</span></div>
          <div className="detailSection">
            <h3>Raw Payload</h3>
            <pre className="payloadView">{job.payload || 'No payload'}</pre>
          </div>
        </div>
      </div>
    </div>
  );

  const renderContent = () => {
    if (selectedJob) {
      return <JobDetailModal job={selectedJob} onClose={() => setSelectedJob(null)} />;
    }

    switch (tab) {
      case 'Job Search':
        return <JobSearchContent />;
      case 'Ingestion Monitor':
        return (
          <div className="card pad">
            <h2>Ingestion Monitor</h2>
            <div className="statsGrid">
              <div className="statCard"><small>Total Raw Jobs</small><b>{jobCount.toLocaleString()}</b></div>
              <div className="statCard"><small>Sources Active</small><b>{sweep?.sources ? Object.keys(sweep.sources).length : 0}</b></div>
              <div className="statCard"><small>Last Sweep</small><b>{sweep?.lastSweep ? new Date(sweep.lastSweep).toLocaleString() : 'Pending'}</b></div>
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
              <div className="sourceGrid">
                {Object.entries(sweep.sources).map(([name, info]) => (
                  <div key={name} className="sourceCard">
                    <span className="sourceName">{name}</span>
                    <span className="sourceInfo">{info.jobs} jobs — {info.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      default:
        return (
          <div className="card pad">
            <h2>{tab || items[0]}</h2>
            <p>Authenticated workspace with backend-enforced role access.</p>
            {primary === 'ADMIN' && sweep?.sources && (
              <div style={{ marginTop: 16 }}>
                <h3>Source Status</h3>
                <div className="sourceGrid">
                  {Object.entries(sweep.sources).map(([name, info]) => (
                    <div key={name} className="sourceCard">
                      <span className="sourceName">{name}</span>
                      <span className="sourceInfo">{info.jobs} jobs — {info.status}</span>
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
    <div className="dashboardLayout">
      <aside className="sidebar">
        <div className="brand light">Job<span>Hub</span></div>
        <div className="tenantLabel">{user.tenantKey}</div>
        <nav className="sidebarNav">
          {items.map(x => (
            <button key={x} className={`navItem ${tab === x ? 'active' : ''}`} onClick={() => setTab(x)}>{x}</button>
          ))}
        </nav>
        <div className="sidebarFooter">
          <button className="signOutBtn" onClick={() => { localStorage.clear(); router.push('/'); }}>↪ Sign out</button>
        </div>
      </aside>
      <main className="dashboardMain">
        <header className="dashboardHeader">
          <div><b>JobHub</b><span> / {tab || items[0]}</span></div>
          <div className="userBadge">
            <span className="avatar">{user.displayName?.slice(0, 2).toUpperCase()}</span>
            <div><b>{user.displayName}</b><small>{primary}</small></div>
          </div>
        </header>
        <div className="dashboardContent">
          {renderContent()}
          {tab !== 'Job Search' && tab !== 'Ingestion Monitor' && tab !== 'Sweep Status' && jobs.length > 0 && (
            <div className="card pad" style={{ marginTop: 16 }}>
              <h3>Recent Jobs ({jobCount.toLocaleString()} total)</h3>
              {jobs.slice(0, 3).map(job => (
                <div key={job.id} className="jobCard" onClick={() => setSelectedJob(job)}>
                  <b>{job.externalJobId}</b>
                  <small style={{ color: 'var(--muted)', marginLeft: 8 }}>{new Date(job.fetchedAt).toLocaleDateString()}</small>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
