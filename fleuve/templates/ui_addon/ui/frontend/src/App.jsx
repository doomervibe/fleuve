import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import WorkflowList from './components/WorkflowList';
import WorkflowDetail from './components/WorkflowDetail';
import EventExplorer from './components/EventExplorer';
import ActivityMonitor from './components/ActivityMonitor';
import DelayViewer from './components/DelayViewer';
import { isMockMode } from './api';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import HelpOverlay from './components/common/HelpOverlay';
import './App.css';

function Navigation() {
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'dashboard', exact: true, icon: '[D]' },
    { path: '/workflows', label: 'workflows', icon: '[W]' },
    { path: '/events', label: 'events', icon: '[E]' },
    { path: '/activities', label: 'activities', icon: '[A]' },
    { path: '/delays', label: 'delays', icon: '[T]' },
  ];

  return (
    <header className="header">
      <div className="header-content">
        <div className="header-left">
          <Link to="/" className="logo-link">
            <h1 className="logo">fleuve</h1>
          </Link>
          {isMockMode && (
            <span className="nav-badge nav-badge--pending">mock</span>
          )}
          <nav className="nav">
            {navItems.map((item) => {
              const isActive = item.exact
                ? location.pathname === item.path
                : location.pathname.startsWith(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={isActive ? 'active' : ''}
                  end={item.exact}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="header-right">
          <span className="status healthy">
            <span className="status-dot" />
            connected
          </span>
        </div>
      </div>
    </header>
  );
}

function AppContent() {
  const { helpOpen, setHelpOpen, shortcuts } = useKeyboardShortcuts({
    onFocusSearch: () => {
      const el = document.querySelector('[data-search-input]');
      if (el) el.focus();
    },
  });

  return (
    <>
      <div className="app">
        <Navigation />
        <main className="main-content">
          <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/workflows" element={<WorkflowList />} />
              <Route path="/workflows/:workflowId" element={<WorkflowDetail />} />
              <Route path="/events" element={<EventExplorer />} />
              <Route path="/activities" element={<ActivityMonitor />} />
              <Route path="/delays" element={<DelayViewer />} />
          </Routes>
        </main>
      </div>
      <HelpOverlay
        shortcuts={shortcuts}
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
      />
    </>
  );
}

function App() {
  return (
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
  );
}

export default App;
