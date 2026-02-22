import { useState, useEffect } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import './App.css';
import Dashboard from './components/Dashboard';
import WorkflowDetail from './components/WorkflowDetail';
import EventsList from './components/EventsList';
import ActivitiesList from './components/ActivitiesList';
import DelaysList from './components/DelaysList';
import RunnersList from './components/RunnersList';
import Header from './components/Header';
import { api } from './api/client';

function App() {
  const navigate = useNavigate();
  useKeyboardShortcuts();
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
    navigate(`/workflows/${workflowId}`);
  };

  const handleBackToDashboard = () => {
    navigate('/');
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
      <Header isHealthy={isHealthy} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard onViewWorkflow={handleViewWorkflow} />} />
          <Route path="/workflows/:id" element={<WorkflowDetail onBack={handleBackToDashboard} />} />
          <Route path="/events" element={<EventsList onViewWorkflow={handleViewWorkflow} />} />
          <Route path="/activities" element={<ActivitiesList onViewWorkflow={handleViewWorkflow} />} />
          <Route path="/delays" element={<DelaysList onViewWorkflow={handleViewWorkflow} />} />
          <Route path="/runners" element={<RunnersList />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
