import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import WorkflowList from './components/WorkflowList';
import WorkflowDetail from './components/WorkflowDetail';
import EventExplorer from './components/EventExplorer';
import ActivityMonitor from './components/ActivityMonitor';
import DelayViewer from './components/DelayViewer';
import { isMockMode } from './api';

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
    <nav className="bg-black border-b border-[#00ff00] sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-2">
        <div className="flex items-center justify-between h-10">
          <div className="flex items-center space-x-2">
            <span className="text-[#00ff00] font-mono text-sm">$</span>
            <h1 className="text-sm font-mono text-[#00ff00]">
              fleuve
            </h1>
            {isMockMode && (
              <span className="ml-2 px-1 py-0 text-xs font-mono bg-black text-[#ffbf00] border border-[#ffbf00]">
                [MOCK]
              </span>
            )}
          </div>
          <div className="flex space-x-1">
            {navItems.map((item) => {
              const isActive = item.exact
                ? location.pathname === item.path
                : location.pathname.startsWith(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-2 py-1 text-xs font-mono border flex items-center space-x-1 ${
                    isActive
                      ? 'bg-[#003300] text-[#00ff00] border-[#00ff00]'
                      : 'text-[#00ff00] border-[#00ff00] hover:bg-[#001100]'
                  }`}
                >
                  <span className="text-xs">{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-black text-[#00ff00]">
        <Navigation />
        <main className="max-w-7xl mx-auto px-2 py-2">
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
    </BrowserRouter>
  );
}

export default App;
