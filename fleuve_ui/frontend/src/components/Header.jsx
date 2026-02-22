export default function Header({ currentView, onNavigate, isHealthy }) {
  return (
    <header className="header">
      <div className="header-content">
        <div className="header-left">
          <h1 className="logo">fleuve</h1>
          <nav className="nav">
            <button
              className={currentView === 'dashboard' ? 'active' : ''}
              onClick={() => onNavigate('dashboard')}
            >
              workflows
            </button>
            <button
              className={currentView === 'events' ? 'active' : ''}
              onClick={() => onNavigate('events')}
            >
              events
            </button>
            <button
              className={currentView === 'activities' ? 'active' : ''}
              onClick={() => onNavigate('activities')}
            >
              activities
            </button>
            <button
              className={currentView === 'delays' ? 'active' : ''}
              onClick={() => onNavigate('delays')}
            >
              delays
            </button>
            <button
              className={currentView === 'runners' ? 'active' : ''}
              onClick={() => onNavigate('runners')}
            >
              runners
            </button>
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
