import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import { format } from 'date-fns';

function CopyButton({ text, className = '' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className={`inline-flex items-center gap-1 px-1 py-0 text-xs font-mono text-[#00ff00] hover:text-[#00ffff] border border-[#00ff00] ${className}`}
      title="Copy to clipboard"
    >
      {copied ? (
        <>
          <span>[OK]</span>
        </>
      ) : (
        <>
          <span>[CP]</span>
        </>
      )}
    </button>
  );
}

export default function WorkflowDetail() {
  const { workflowId } = useParams();
  const [workflow, setWorkflow] = useState(null);
  const [events, setEvents] = useState([]);
  const [activities, setActivities] = useState([]);
  const [delays, setDelays] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [stateAtVersion, setStateAtVersion] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [workflowData, eventsData, activitiesData, delaysData] = await Promise.all([
        api.getWorkflow(workflowId),
        api.getWorkflowEvents(workflowId),
        api.getWorkflowActivities(workflowId),
        api.getWorkflowDelays(workflowId),
      ]);
      setWorkflow(workflowData);
      setEvents(eventsData);
      setActivities(activitiesData);
      setDelays(delaysData);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [workflowId]);

  const handleVersionSelect = async (version) => {
    setSelectedVersion(version);
    try {
      const stateData = await api.getWorkflowStateAtVersion(workflowId, version);
      setStateAtVersion(stateData);
    } catch (err) {
      console.error('Failed to load state at version:', err);
      setStateAtVersion(null);
    }
  };

  if (loading && !workflow) {
    return <Loading message="> loading workflow..." />;
  }

  if (error) {
    return <Error error={error} onRetry={fetchData} />;
  }

  if (!workflow) {
    return null;
  }

  const tabs = [
    { id: 'overview', label: 'overview' },
    { id: 'events', label: 'events' },
    { id: 'activities', label: 'activities' },
    { id: 'delays', label: 'delays' },
    { id: 'state', label: 'state' },
  ];

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/workflows" className="text-[#00ff00] hover:text-[#00ffff] text-xs font-mono">
            ← back_to_workflows
          </Link>
          <h2 className="text-sm font-mono text-[#00ff00] mt-0">$ workflow_details</h2>
          <div className="mt-0 flex items-center gap-1">
            <p className="text-xs text-[#00ff00] font-mono opacity-70">{workflow.workflow_id}</p>
            <CopyButton text={workflow.workflow_id} />
          </div>
        </div>
      </div>

      {/* Workflow Info Card */}
      <div className="card p-2">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <p className="text-xs font-mono text-[#00ff00] opacity-70">workflow_type:</p>
            <p className="mt-0 text-xs font-mono text-[#00ff00]">{workflow.workflow_type}</p>
          </div>
          <div>
            <p className="text-xs font-mono text-[#00ff00] opacity-70">version:</p>
            <p className="mt-0 text-xs font-mono text-[#00ff00]">{workflow.version}</p>
          </div>
          <div>
            <p className="text-xs font-mono text-[#00ff00] opacity-70">status:</p>
            <p className="mt-0 text-xs font-mono">
              {workflow.is_completed ? (
                <span className="px-1 py-0 bg-black text-[#00ff00] border border-[#00ff00]">completed</span>
              ) : (
                <span className="px-1 py-0 bg-black text-[#00ffff] border border-[#00ffff]">active</span>
              )}
            </p>
          </div>
          <div>
            <p className="text-xs font-mono text-[#00ff00] opacity-70">created:</p>
            <p className="mt-0 text-xs font-mono text-[#00ff00]">
              {workflow.created_at
                ? format(new Date(workflow.created_at), 'MMM d, yyyy HH:mm:ss')
                : 'N/A'}
            </p>
          </div>
          <div>
            <p className="text-xs font-mono text-[#00ff00] opacity-70">last_updated:</p>
            <p className="mt-0 text-xs font-mono text-[#00ff00]">
              {workflow.updated_at
                ? format(new Date(workflow.updated_at), 'MMM d, yyyy HH:mm:ss')
                : 'N/A'}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="card">
        <div className="border-b border-[#00ff00]">
          <nav className="flex -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-2 py-1 text-xs font-mono border-b-2 ${
                  activeTab === tab.id
                    ? 'border-[#00ff00] text-[#00ff00] bg-[#001100]'
                    : 'border-transparent text-[#00ff00] opacity-70 hover:opacity-100 hover:border-[#00ff00]'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-2">
          {activeTab === 'overview' && (
            <div className="space-y-1">
              <div>
                <h3 className="text-xs font-mono text-[#00ff00] mb-1">current_state:</h3>
                <pre className="bg-black p-2 overflow-x-auto text-xs font-mono text-[#00ff00] border border-[#00ff00]">
                  {JSON.stringify(workflow.state, null, 2)}
                </pre>
              </div>
              {workflow.subscriptions.length > 0 && (
                <div>
                  <h3 className="text-xs font-mono text-[#00ff00] mb-1">subscriptions:</h3>
                  <div className="space-y-1">
                    {workflow.subscriptions.map((sub, idx) => (
                      <div key={idx} className="bg-black p-2 border border-[#00ff00]">
                        <p className="text-xs font-mono text-[#00ff00]">
                          <span className="opacity-70">workflow:</span> {sub.workflow_id}
                        </p>
                        <p className="text-xs font-mono text-[#00ff00]">
                          <span className="opacity-70">event_type:</span> {sub.event_type}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'events' && (
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-mono text-[#00ff00]">event_timeline:</h3>
                <div className="flex items-center space-x-1">
                  <label className="text-xs font-mono text-[#00ff00] opacity-70">view_state_at_version:</label>
                  <select
                    value={selectedVersion || ''}
                    onChange={(e) => handleVersionSelect(parseInt(e.target.value))}
                    className="px-2 py-1 bg-black border border-[#00ff00] text-xs font-mono text-[#00ff00]"
                  >
                    <option value="">current</option>
                    {events.map((e) => (
                      <option key={e.workflow_version} value={e.workflow_version}>
                        version {e.workflow_version}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              {events.length > 0 ? (
                <div className="space-y-1">
                  {events.map((event, idx) => (
                    <div
                      key={idx}
                      className="border-l-2 border-[#00ff00] pl-2 py-1 bg-black"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-mono text-xs text-[#00ff00]">{event.event_type}</p>
                          <p className="text-xs font-mono text-[#00ff00] opacity-70">
                            version {event.workflow_version} |{' '}
                            {format(new Date(event.at), 'MMM d, yyyy HH:mm:ss')}
                          </p>
                        </div>
                        <span className="text-xs font-mono text-[#00ff00] opacity-50">#{event.global_id}</span>
                      </div>
                      <details className="mt-0">
                        <summary className="text-xs font-mono text-[#00ffff] cursor-pointer">
                          view_event_body
                        </summary>
                        <pre className="mt-0 bg-black p-2 border border-[#00ff00] text-xs font-mono overflow-x-auto text-[#00ff00]">
                          {JSON.stringify(event.body, null, 2)}
                        </pre>
                      </details>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[#00ff00] opacity-50 text-center py-4 font-mono text-xs">> no events found</p>
              )}
            </div>
          )}

          {activeTab === 'activities' && (
            <div className="space-y-1">
              <h3 className="text-xs font-mono text-[#00ff00]">activities:</h3>
              {activities.length > 0 ? (
                <div className="overflow-x-auto border border-[#00ff00]">
                  <table className="min-w-full divide-y divide-[#00ff00] font-mono text-xs">
                    <thead className="bg-black">
                      <tr>
                        <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                          event_#
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                          status
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                          retries
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                          started
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                          finished
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                          error
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-black divide-y divide-[#00ff00]">
                      {activities.map((activity, idx) => (
                        <tr key={idx}>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-[#00ff00]">
                            {activity.event_number}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap">
                            <span
                              className={`px-1 py-0 text-xs font-mono border ${
                                activity.status === 'completed'
                                  ? 'bg-black text-[#00ff00] border-[#00ff00]'
                                  : activity.status === 'failed'
                                  ? 'bg-black text-[#ff0000] border-[#ff0000]'
                                  : activity.status === 'running'
                                  ? 'bg-black text-[#00ffff] border-[#00ffff]'
                                  : 'bg-black text-[#ffbf00] border-[#ffbf00]'
                              }`}
                            >
                              {activity.status}
                            </span>
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-[#00ff00]">
                            {activity.retry_count} / {activity.max_retries}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-[#00ff00] opacity-70">
                            {format(new Date(activity.started_at), 'MMM d, HH:mm:ss')}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-[#00ff00] opacity-70">
                            {activity.finished_at
                              ? format(new Date(activity.finished_at), 'MMM d, HH:mm:ss')
                              : '-'}
                          </td>
                          <td className="px-2 py-1 text-xs text-[#ff0000]">
                            {activity.error_message ? (
                              <span title={activity.error_type}>
                                {activity.error_message.substring(0, 50)}...
                              </span>
                            ) : (
                              '-'
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-[#00ff00] opacity-50 text-center py-4 font-mono text-xs">> no activities found</p>
              )}
            </div>
          )}

          {activeTab === 'delays' && (
            <div className="space-y-1">
              <h3 className="text-xs font-mono text-[#00ff00]">scheduled_delays:</h3>
              {delays.length > 0 ? (
                <div className="space-y-1">
                  {delays.map((delay, idx) => {
                    const now = new Date();
                    const delayUntil = new Date(delay.delay_until);
                    const isActive = delayUntil > now;
                    return (
                      <div
                        key={idx}
                        className={`border-l-2 ${
                          isActive ? 'border-[#ffbf00]' : 'border-[#00ff00]'
                        } pl-2 py-1 bg-black`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-mono text-xs text-[#00ff00]">
                              {isActive ? 'scheduled' : 'completed'}
                            </p>
                            <p className="text-xs font-mono text-[#00ff00] opacity-70">
                              until: {format(delayUntil, 'MMM d, yyyy HH:mm:ss')}
                            </p>
                            <p className="text-xs font-mono text-[#00ff00] opacity-70">
                              event_version: {delay.event_version}
                            </p>
                          </div>
                          {isActive && (
                            <span className="text-xs font-mono text-[#ffbf00]">
                              {Math.ceil((delayUntil - now) / 1000 / 60)} min remaining
                            </span>
                          )}
                        </div>
                        <details className="mt-0">
                          <summary className="text-xs font-mono text-[#00ffff] cursor-pointer">
                            view_next_command
                          </summary>
                          <pre className="mt-0 bg-black p-2 border border-[#00ff00] text-xs font-mono overflow-x-auto text-[#00ff00]">
                            {JSON.stringify(delay.next_command, null, 2)}
                          </pre>
                        </details>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[#00ff00] opacity-50 text-center py-4 font-mono text-xs">> no delays found</p>
              )}
            </div>
          )}

          {activeTab === 'state' && (
            <div className="space-y-1">
              <h3 className="text-xs font-mono text-[#00ff00]">state:</h3>
              {selectedVersion && stateAtVersion ? (
                <div>
                  <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-1">
                    state at version {selectedVersion} (time travel)
                  </p>
                  <pre className="bg-black p-2 overflow-x-auto text-xs font-mono text-[#00ff00] border border-[#00ff00]">
                    {JSON.stringify(stateAtVersion, null, 2)}
                  </pre>
                </div>
              ) : (
                <div>
                  <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-1">current state</p>
                  <pre className="bg-black p-2 overflow-x-auto text-xs font-mono text-[#00ff00] border border-[#00ff00]">
                    {JSON.stringify(workflow.state, null, 2)}
                  </pre>
                  <p className="mt-2 text-xs font-mono text-[#00ff00] opacity-70">
                    select a version from the events tab to view state at that point in time.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
