import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import JsonTree from './common/JsonTree';
import StateDiff from './common/StateDiff';
import WorkflowTimeline from './common/WorkflowTimeline';
import { format, formatDistanceToNow } from 'date-fns';

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
      className={`inline-flex items-center gap-1 px-1 py-0 text-xs font-mono text-theme hover:text-theme-accent border border-theme ${className}`}
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
  const [diffMode, setDiffMode] = useState(false);
  const [diffVersion1, setDiffVersion1] = useState(null);
  const [diffVersion2, setDiffVersion2] = useState(null);
  const [stateDiff, setStateDiff] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [now, setNow] = useState(new Date());
  const eventRefs = useRef({});

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

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

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

  const handleDiffFetch = async () => {
    if (!diffVersion1 || !diffVersion2) return;
    try {
      const data = await api.getWorkflowStateDiff(workflowId, diffVersion1, diffVersion2);
      setStateDiff(data);
    } catch (err) {
      console.error('Failed to load state diff:', err);
      setStateDiff(null);
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

  const pendingActivities = activities.filter(
    (a) => a.status === 'pending' || a.status === 'retrying'
  );
  const activeDelays = delays.filter((d) => new Date(d.delay_until) > now);
  const pendingCount = pendingActivities.length + activeDelays.length;

  const tabs = [
    { id: 'overview', label: 'overview' },
    { id: 'pending', label: 'pending', badge: pendingCount },
    { id: 'events', label: 'events' },
    { id: 'activities', label: 'activities' },
    { id: 'delays', label: 'delays' },
    { id: 'state', label: 'state' },
  ];

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/workflows" className="text-theme hover:text-theme-accent text-xs font-mono">
            ← back_to_workflows
          </Link>
          <h2 className="text-sm font-mono text-theme mt-0">$ workflow_details</h2>
          <div className="mt-0 flex items-center gap-1">
            <p className="text-xs text-theme font-mono opacity-70">{workflow.workflow_id}</p>
            <CopyButton text={workflow.workflow_id} />
          </div>
        </div>
      </div>

      {/* Workflow Info Card */}
      <div className="card p-2">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <p className="text-xs font-mono text-theme opacity-70">workflow_type:</p>
            <p className="mt-0 text-xs font-mono text-theme">{workflow.workflow_type}</p>
          </div>
          <div>
            <p className="text-xs font-mono text-theme opacity-70">version:</p>
            <p className="mt-0 text-xs font-mono text-theme">{workflow.version}</p>
          </div>
          <div>
            <p className="text-xs font-mono text-theme opacity-70">status:</p>
            <p className="mt-0 text-xs font-mono">
              {workflow.is_completed ? (
                <span className="px-1 py-0 bg-theme text-theme border border-theme">completed</span>
              ) : (
                <span className="px-1 py-0 bg-theme text-theme-accent border border-theme-accent">active</span>
              )}
            </p>
          </div>
          <div>
            <p className="text-xs font-mono text-theme opacity-70">created:</p>
            <p className="mt-0 text-xs font-mono text-theme">
              {workflow.created_at
                ? format(new Date(workflow.created_at), 'MMM d, yyyy HH:mm:ss')
                : 'N/A'}
            </p>
          </div>
          <div>
            <p className="text-xs font-mono text-theme opacity-70">last_updated:</p>
            <p className="mt-0 text-xs font-mono text-theme">
              {workflow.updated_at
                ? format(new Date(workflow.updated_at), 'MMM d, yyyy HH:mm:ss')
                : 'N/A'}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="card">
        <div className="border-b border-theme">
          <nav className="flex -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-2 py-1 text-xs font-mono border-b-2 flex items-center gap-1 ${
                  activeTab === tab.id
                    ? 'border-theme text-theme bg-[var(--fleuve-border-hover)]'
                    : 'border-transparent text-theme opacity-70 hover:opacity-100 hover:border-theme'
                }`}
              >
                {tab.label}
                {tab.badge != null && tab.badge > 0 && (
                  <span className="px-1 py-0 text-[10px] bg-theme-warning text-theme border border-theme-warning">
                    {tab.badge}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-2">
          {activeTab === 'overview' && (
            <div className="space-y-1">
              <div>
                <h3 className="text-xs font-mono text-theme mb-1">current_state:</h3>
                <JsonTree data={workflow.state} />
              </div>
              {workflow.subscriptions.length > 0 && (
                <div>
                  <h3 className="text-xs font-mono text-theme mb-1">subscriptions:</h3>
                  <div className="space-y-1">
                    {workflow.subscriptions.map((sub, idx) => (
                      <div key={idx} className="bg-theme p-2 border border-theme">
                        <p className="text-xs font-mono text-theme">
                          <span className="opacity-70">workflow:</span> {sub.workflow_id}
                        </p>
                        <p className="text-xs font-mono text-theme">
                          <span className="opacity-70">event_type:</span> {sub.event_type}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'pending' && (
            <div className="space-y-1">
              <h3 className="text-xs font-mono text-theme mb-2">pending_activities_and_timers:</h3>
              {pendingCount === 0 ? (
                <p className="text-theme opacity-50 text-center py-4 font-mono text-xs">> no pending items</p>
              ) : (
                <div className="space-y-2">
                  {pendingActivities.length > 0 && (
                    <div>
                      <h4 className="text-xs font-mono text-theme opacity-70 mb-1">
                        pending_activities ({pendingActivities.length})
                      </h4>
                      <div className="space-y-1">
                        {pendingActivities.map((activity, idx) => (
                          <div
                            key={idx}
                            className="border-l-2 border-theme-warning pl-2 py-1 bg-theme"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-xs text-theme">
                                event #{activity.event_number}
                              </span>
                              <span className="text-xs font-mono text-theme-warning">
                                {activity.status}
                              </span>
                            </div>
                            <p className="text-xs font-mono text-theme opacity-70 mt-0">
                              retries: {activity.retry_count} / {activity.max_retries}
                              {activity.started_at && (
                                <> · waiting {formatDistanceToNow(new Date(activity.started_at), { addSuffix: false })}</>
                              )}
                            </p>
                            {activity.error_message && (
                              <p className="text-xs font-mono text-theme-error mt-0 truncate" title={activity.error_message}>
                                {activity.error_message.substring(0, 60)}...
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {activeDelays.length > 0 && (
                    <div>
                      <h4 className="text-xs font-mono text-theme opacity-70 mb-1">
                        active_timers ({activeDelays.length})
                      </h4>
                      <div className="space-y-1">
                        {activeDelays.map((delay, idx) => {
                          const delayUntil = new Date(delay.delay_until);
                          const remaining = delayUntil - now;
                          const remainingSec = Math.max(0, Math.floor(remaining / 1000));
                          const mins = Math.floor(remainingSec / 60);
                          const secs = remainingSec % 60;
                          const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                          return (
                            <div
                              key={idx}
                              className="border-l-2 border-theme-warning pl-2 py-1 bg-theme"
                            >
                              <div className="flex items-center justify-between">
                                <div>
                                  <p className="font-mono text-xs text-theme">
                                    until {format(delayUntil, 'MMM d, HH:mm:ss')}
                                  </p>
                                  <p className="text-xs font-mono text-theme opacity-70">
                                    event_version: {delay.event_version}
                                  </p>
                                </div>
                                <span className="text-xs font-mono text-theme-warning font-medium">
                                  {timeStr}
                                </span>
                              </div>
                              <p className="text-xs font-mono text-theme opacity-50 mt-0">
                                {formatDistanceToNow(delayUntil, { addSuffix: true })}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {activeTab === 'events' && (
            <div className="space-y-1">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h3 className="text-xs font-mono text-theme">event_timeline:</h3>
                <div className="flex items-center space-x-2 flex-wrap">
                  <label className="flex items-center gap-1 text-xs font-mono text-theme opacity-70">
                    <input
                      type="checkbox"
                      checked={diffMode}
                      onChange={(e) => {
                        setDiffMode(e.target.checked);
                        if (!e.target.checked) setStateDiff(null);
                      }}
                      className="border border-theme"
                    />
                    diff
                  </label>
                  {!diffMode ? (
                    <>
                      <label className="text-xs font-mono text-theme opacity-70">view_state_at_version:</label>
                      <select
                        value={selectedVersion || ''}
                        onChange={(e) => handleVersionSelect(parseInt(e.target.value) || null)}
                        className="px-2 py-1 bg-theme border border-theme text-xs font-mono text-theme"
                      >
                        <option value="">current</option>
                        {events.map((e) => (
                          <option key={e.workflow_version} value={e.workflow_version}>
                            version {e.workflow_version}
                          </option>
                        ))}
                      </select>
                    </>
                  ) : (
                    <>
                      <select
                        value={diffVersion1 || ''}
                        onChange={(e) => setDiffVersion1(parseInt(e.target.value) || null)}
                        className="px-2 py-1 bg-theme border border-theme text-xs font-mono text-theme"
                      >
                        <option value="">v1</option>
                        {events.map((e) => (
                          <option key={e.workflow_version} value={e.workflow_version}>
                            v{e.workflow_version}
                          </option>
                        ))}
                      </select>
                      <span className="text-theme opacity-70">→</span>
                      <select
                        value={diffVersion2 || ''}
                        onChange={(e) => setDiffVersion2(parseInt(e.target.value) || null)}
                        className="px-2 py-1 bg-theme border border-theme text-xs font-mono text-theme"
                      >
                        <option value="">v2</option>
                        {events.map((e) => (
                          <option key={e.workflow_version} value={e.workflow_version}>
                            v{e.workflow_version}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={handleDiffFetch}
                        disabled={!diffVersion1 || !diffVersion2}
                        className="px-2 py-1 bg-theme border border-theme text-theme text-xs font-mono hover:bg-[var(--fleuve-border-hover)] disabled:opacity-50"
                      >
                        show_diff
                      </button>
                    </>
                  )}
                </div>
              </div>
              {diffMode && stateDiff ? (
                <div className="mt-2">
                  <StateDiff
                    stateV1={stateDiff.state_v1}
                    stateV2={stateDiff.state_v2}
                    label1={`v${stateDiff.version1}`}
                    label2={`v${stateDiff.version2}`}
                  />
                </div>
              ) : diffMode && (diffVersion1 || diffVersion2) && !stateDiff ? (
                <p className="text-theme opacity-50 text-center py-4 font-mono text-xs">
                  select both versions and click show_diff
                </p>
              ) : events.length > 0 ? (
                <div className="space-y-1">
                  <WorkflowTimeline
                    events={events}
                    activities={activities}
                    delays={delays}
                    onEventClick={(event, index) => {
                      const el = eventRefs.current[index];
                      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }}
                    eventRefs={eventRefs}
                  />
                  {events.map((event, idx) => (
                    <div
                      key={idx}
                      ref={(el) => { eventRefs.current[idx] = el; }}
                      className="border-l-2 border-theme pl-2 py-1 bg-theme"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-mono text-xs text-theme">{event.event_type}</p>
                          <p className="text-xs font-mono text-theme opacity-70">
                            version {event.workflow_version} |{' '}
                            {format(new Date(event.at), 'MMM d, yyyy HH:mm:ss')}
                          </p>
                        </div>
                        <span className="text-xs font-mono text-theme opacity-50">#{event.global_id}</span>
                      </div>
                      <details className="mt-0">
                        <summary className="text-xs font-mono text-theme-accent cursor-pointer">
                          view_event_body
                        </summary>
                        <JsonTree data={event.body} className="mt-1" />
                      </details>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-theme opacity-50 text-center py-4 font-mono text-xs">> no events found</p>
              )}
            </div>
          )}

          {activeTab === 'activities' && (
            <div className="space-y-1">
              <h3 className="text-xs font-mono text-theme">activities:</h3>
              {activities.length > 0 ? (
                <div className="overflow-x-auto border border-theme">
                  <table className="min-w-full divide-y divide-[color:var(--fleuve-border)] font-mono text-xs">
                    <thead className="bg-theme">
                      <tr>
                        <th className="px-2 py-1 text-left text-xs font-mono text-theme border-b border-theme">
                          event_#
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-theme border-b border-theme">
                          status
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-theme border-b border-theme">
                          retries
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-theme border-b border-theme">
                          started
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-theme border-b border-theme">
                          finished
                        </th>
                        <th className="px-2 py-1 text-left text-xs font-mono text-theme border-b border-theme">
                          error
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-theme divide-y divide-[color:var(--fleuve-border)]">
                      {activities.map((activity, idx) => (
                        <tr key={idx}>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-theme">
                            {activity.event_number}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap">
                            <span
                              className={`px-1 py-0 text-xs font-mono border ${
                                activity.status === 'completed'
                                  ? 'bg-theme text-theme border-theme'
                                  : activity.status === 'failed'
                                  ? 'bg-theme text-theme-error border-theme-error'
                                  : activity.status === 'running'
                                  ? 'bg-theme text-theme-accent border-theme-accent'
                                  : 'bg-theme text-theme-warning border-theme-warning'
                              }`}
                            >
                              {activity.status}
                            </span>
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-theme">
                            {activity.retry_count} / {activity.max_retries}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-theme opacity-70">
                            {format(new Date(activity.started_at), 'MMM d, HH:mm:ss')}
                          </td>
                          <td className="px-2 py-1 whitespace-nowrap text-xs text-theme opacity-70">
                            {activity.finished_at
                              ? format(new Date(activity.finished_at), 'MMM d, HH:mm:ss')
                              : '-'}
                          </td>
                          <td className="px-2 py-1 text-xs text-theme-error">
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
                <p className="text-theme opacity-50 text-center py-4 font-mono text-xs">> no activities found</p>
              )}
            </div>
          )}

          {activeTab === 'delays' && (
            <div className="space-y-1">
              <h3 className="text-xs font-mono text-theme">scheduled_delays:</h3>
              {delays.length > 0 ? (
                <div className="space-y-1">
                  {delays.map((delay, idx) => {
                    const delayUntil = new Date(delay.delay_until);
                    const isActive = delayUntil > now;
                    return (
                      <div
                        key={idx}
                        className={`border-l-2 ${
                          isActive ? 'border-theme-warning' : 'border-theme'
                        } pl-2 py-1 bg-theme`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-mono text-xs text-theme">
                              {isActive ? 'scheduled' : 'completed'}
                            </p>
                            <p className="text-xs font-mono text-theme opacity-70">
                              until: {format(delayUntil, 'MMM d, yyyy HH:mm:ss')}
                            </p>
                            <p className="text-xs font-mono text-theme opacity-70">
                              event_version: {delay.event_version}
                            </p>
                            {delay.cron_expression && (
                              <p className="text-xs font-mono text-theme-accent mt-0">
                                cron: {delay.cron_expression}
                                {delay.next_fire_times?.length > 0 && (
                                  <span className="opacity-70 ml-1">
                                    next: {delay.next_fire_times.slice(0, 3).map((t, i) => format(new Date(t), 'MMM d HH:mm')).join(', ')}
                                  </span>
                                )}
                              </p>
                            )}
                          </div>
                          {isActive && (
                            <span className="text-xs font-mono text-theme-warning">
                              {Math.max(0, Math.floor((delayUntil - now) / 1000))}s remaining
                            </span>
                          )}
                        </div>
                        <details className="mt-0">
                          <summary className="text-xs font-mono text-theme-accent cursor-pointer">
                            view_next_command
                          </summary>
                          <JsonTree data={delay.next_command} className="mt-1" />
                        </details>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-theme opacity-50 text-center py-4 font-mono text-xs">> no delays found</p>
              )}
            </div>
          )}

          {activeTab === 'state' && (
            <div className="space-y-1">
              <h3 className="text-xs font-mono text-theme">state:</h3>
              {selectedVersion && stateAtVersion ? (
                <div>
                  <p className="text-xs font-mono text-theme opacity-70 mb-1">
                    state at version {selectedVersion} (time travel)
                  </p>
                  <JsonTree data={stateAtVersion} />
                </div>
              ) : (
                <div>
                  <p className="text-xs font-mono text-theme opacity-70 mb-1">current state</p>
                  <JsonTree data={workflow.state} />
                  <p className="mt-2 text-xs font-mono text-theme opacity-70">
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
