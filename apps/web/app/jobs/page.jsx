'use client';
import { useState, useEffect } from 'react';

export default function JobSearch() {
  const [query, setQuery] = useState('');
  const [location, setLocation] = useState('');
  const [company, setCompany] = useState('');
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const search = async (p = 0) => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (query) params.set('q', query);
      if (location) params.set('location', location);
      if (company) params.set('company', company);
      params.set('page', p.toString());
      params.set('size', '20');

      const res = await fetch(`/api/v1/jobs/search?${params}`);
      const data = await res.json();
      setResults(data.jobs || []);
      setTotal(data.total || 0);
      setPage(p);
    } catch (err) {
      setError('Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { search(); }, []);

  const totalPages = Math.ceil(total / 20);

  return (
    <main className="searchPage">
      <div className="wrap">
        <h1>Job Search</h1>
        <p style={{ color: 'var(--muted)' }}>Search across {total.toLocaleString()}+ jobs from multiple sources</p>

        <div className="searchFilters">
          <input
            placeholder="Job title, skills, keywords..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
          />
          <input
            placeholder="Location"
            value={location}
            onChange={e => setLocation(e.target.value)}
          />
          <input
            placeholder="Company"
            value={company}
            onChange={e => setCompany(e.target.value)}
          />
          <button className="btn primary" onClick={() => search()}>Search</button>
        </div>

        {error && <div className="error">{error}</div>}
        {loading && <div className="loading">Searching...</div>}

        <div className="searchResults">
          {results.map(job => (
            <div key={job.id} className="jobCard">
              <h3>{job.externalJobId || 'Job Listing'}</h3>
              <div className="meta">
                <span>Source: {job.sourceId}</span>
                <span>Fetched: {new Date(job.fetchedAt).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>

        {totalPages > 1 && (
          <div className="pagination">
            {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => (
              <button
                key={i}
                className={i === page ? 'active' : ''}
                onClick={() => search(i)}
              >
                {i + 1}
              </button>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
