import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { api } from '../api/client';

export default function Header({ isHealthy }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (!isHealthy) return;
    async function loadStats() {
      try {
        const data = await api.stats?.();
        if (data) setStats(data);
      } catch {
        // ignore
      }
    }
    loadStats();
    const interval = setInterval(loadStats, 30000);
    return () => clearInterval(interval);
  }, [isHealthy]);

  const failedActivities = stats?.failed_activities ?? 0;
  const pendingActivities = stats?.pending_activities ?? 0;

  return (
    <header className="header">
      <div className="header-content">
        <div className="header-left">
          <NavLink to="/" className="logo-link">
            <h1 className="logo">fleuve</h1>
          </NavLink>
          <nav className="nav">
            <NavLink to="/" className={({ isActive: a }) => (a ? 'active' : '')} end>
              workflows
            </NavLink>
            <NavLink to="/events" className={({ isActive: a }) => (a ? 'active' : '')}>
              events
            </NavLink>
            <NavLink to="/activities" className={({ isActive: a }) => (a ? 'active' : '')}>
              activities
              {(failedActivities > 0 || pendingActivities > 0) && (
                <span className="nav-badge">
                  {failedActivities > 0 && (
                    <span className="nav-badge--failed" title="failed">{failedActivities}</span>
                  )}
                  {pendingActivities > 0 && failedActivities === 0 && (
                    <span className="nav-badge--pending" title="pending">{pendingActivities}</span>
                  )}
                </span>
              )}
            </NavLink>
            <NavLink to="/delays" className={({ isActive: a }) => (a ? 'active' : '')}>
              delays
            </NavLink>
            <NavLink to="/runners" className={({ isActive: a }) => (a ? 'active' : '')}>
              runners
            </NavLink>
          </nav>
        </div>
        <div className="header-right">
          <span className={`status ${isHealthy ? 'healthy' : ''}`}>
            <span className="status-dot" />
            {isHealthy ? 'connected' : 'disconnected'}
          </span>
        </div>
      </div>
    </header>
  );
}
