import { useState, useEffect } from 'react';
import './App.css';
import Dashboard from './components/Dashboard';
import WorkflowDetail from './components/WorkflowDetail';
import EventsList from './components/EventsList';
import ActivitiesList from './components/ActivitiesList';
import DelaysList from './components/DelaysList';
import RunnersList from './components/RunnersList';
import Header from './components/Header';
import { api } from './api/client';

const VIEWS = ['dashboard', 'workflow', 'events', 'activities', 'delays', 'runners'];

function App() {
  const [view, setView] = useState('dashboard');
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(null);
  const [isHealthy, setIsHealthy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  async function checkHealth() {
    try {
      await api.health();
      setIsHealthy(true);
    } catch {
      setIsHealthy(false);
    } finally {
      setLoading(false);
    }
  }

  const handleViewWorkflow = (workflowId) => {
    setSelectedWorkflowId(workflowId);
    setView('workflow');
  };

  const handleBackToDashboard = () => {
    setSelectedWorkflowId(null);
    setView('dashboard');
  };

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="spinner" />
          <p>$ connecting...</p>
        </div>
      </div>
    );
  }

  if (!isHealthy) {
    return (
      <div className="app">
        <div className="error">
          <p>ERROR: API server unavailable</p>
          <p className="hint">Cannot connect to Fleuve API</p>
          <p className="hint">Make sure the API server is running</p>
          <button onClick={checkHealth}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <Header currentView={view} onNavigate={setView} isHealthy={isHealthy} />
      <main className="main-content">
        {view === 'dashboard' && (
          <Dashboard onViewWorkflow={handleViewWorkflow} />
        )}
        {view === 'workflow' && selectedWorkflowId && (
          <WorkflowDetail
            workflowId={selectedWorkflowId}
            onBack={handleBackToDashboard}
          />
        )}
        {view === 'events' && (
          <EventsList onViewWorkflow={handleViewWorkflow} />
        )}
        {view === 'activities' && (
          <ActivitiesList onViewWorkflow={handleViewWorkflow} />
        )}
        {view === 'delays' && (
          <DelaysList onViewWorkflow={handleViewWorkflow} />
        )}
        {view === 'runners' && <RunnersList />}
      </main>
    </div>
  );
}

export default App;
