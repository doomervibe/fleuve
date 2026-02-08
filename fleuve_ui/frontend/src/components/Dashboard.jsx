import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';

const COLORS = ['#00ff00', '#00ffff', '#ffbf00', '#ffff00', '#00ff88', '#88ff00', '#ff00ff', '#ff8800'];

function CopyButton({ text, className = '' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
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
      title="Copy workflow ID"
    >
      {copied ? '[OK]' : '[CP]'}
    </button>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [workflowTypes, setWorkflowTypes] = useState([]);
  const [selectedWorkflowType, setSelectedWorkflowType] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Set default workflow type when types are loaded
  useEffect(() => {
    if (workflowTypes.length > 0 && !selectedWorkflowType) {
      setSelectedWorkflowType(workflowTypes[0]);
    }
  }, [workflowTypes, selectedWorkflowType]);

  const fetchWorkflowTypes = async () => {
    try {
      const types = await api.getWorkflowTypes();
      setWorkflowTypes(types.map((t) => t.workflow_type));
    } catch (err) {
      console.error('Failed to fetch workflow types:', err);
    }
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [statsData, workflowsData] = await Promise.all([
        api.getStats(),
        api.getWorkflows({ 
          limit: 10,
          ...(selectedWorkflowType && { workflow_type: selectedWorkflowType })
        }),
      ]);
      setStats(statsData);
      setWorkflows(workflowsData);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkflowTypes();
  }, []);

  // Set default workflow type when types are loaded
  useEffect(() => {
    if (workflowTypes.length > 0 && !selectedWorkflowType) {
      setSelectedWorkflowType(workflowTypes[0]);
    }
  }, [workflowTypes, selectedWorkflowType]);

  useEffect(() => {
    if (selectedWorkflowType) {
      fetchData();
      const interval = setInterval(fetchData, 5000); // Poll every 5 seconds
      return () => clearInterval(interval);
    }
  }, [selectedWorkflowType]);

  if (loading && !stats) {
    return <Loading message="> loading dashboard..." />;
  }

  if (error) {
    return <Error error={error} onRetry={fetchData} />;
  }

  if (!stats) {
    return null;
  }

  // Filter stats based on selected workflow type
  let filteredStats = stats;
  if (selectedWorkflowType) {
    filteredStats = {
      ...stats,
      total_workflows: stats.workflows_by_type?.[selectedWorkflowType] || 0,
      workflows_by_type: {
        [selectedWorkflowType]: stats.workflows_by_type?.[selectedWorkflowType] || 0,
      },
      // Filter events by type that match the workflow type
      events_by_type: Object.fromEntries(
        Object.entries(stats.events_by_type || {}).filter(([key]) => 
          key.startsWith(selectedWorkflowType)
        )
      ),
      total_events: Object.values(
        Object.fromEntries(
          Object.entries(stats.events_by_type || {}).filter(([key]) => 
            key.startsWith(selectedWorkflowType)
          )
        )
      ).reduce((sum, val) => sum + val, 0),
    };
  }

  // Prepare chart data
  const activitiesByStatusData = Object.entries(filteredStats.activities_by_status || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const eventsByTypeData = Object.entries(filteredStats.events_by_type || {})
    .slice(0, 10)
    .map(([name, value]) => ({
      name: name.length > 20 ? name.substring(0, 20) + '...' : name,
      value,
    }));

  return (
    <div className="space-y-1">
      <div className="mb-1">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h2 className="text-sm font-mono text-[#00ff00] mb-0">$ dashboard</h2>
            <p className="text-xs font-mono text-[#00ff00] opacity-70">> overview of your fleuve workflows and system metrics</p>
          </div>
          <div className="flex items-center space-x-2">
            <label className="text-xs font-mono text-[#00ff00]">workflow_type:</label>
            <select
              value={selectedWorkflowType}
              onChange={(e) => setSelectedWorkflowType(e.target.value)}
              className="px-2 py-1 bg-black border border-[#00ff00] text-xs font-mono text-[#00ff00] focus:outline-none focus:border-[#00ffff]"
            >
              {workflowTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-1">
        <div className="stat-card border-l-2 border-l-[#00ff00]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-0">total_workflows:</p>
              <p className="text-lg font-mono text-[#00ff00]">{filteredStats.total_workflows}</p>
            </div>
            <div className="w-8 h-8 bg-black flex items-center justify-center border border-[#00ff00]">
              <span className="text-xs font-mono text-[#00ff00]">[W]</span>
            </div>
          </div>
        </div>

        <div className="stat-card border-l-2 border-l-[#00ff00]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-0">total_events:</p>
              <p className="text-lg font-mono text-[#00ff00]">{filteredStats.total_events}</p>
            </div>
            <div className="w-8 h-8 bg-black flex items-center justify-center border border-[#00ff00]">
              <span className="text-xs font-mono text-[#00ff00]">[E]</span>
            </div>
          </div>
        </div>

        <div className="stat-card border-l-2 border-l-[#00ff00]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-0">pending_activities:</p>
              <p className="text-lg font-mono text-[#00ff00]">{filteredStats.pending_activities}</p>
            </div>
            <div className="w-8 h-8 bg-black flex items-center justify-center border border-[#00ff00]">
              <span className="text-xs font-mono text-[#00ff00]">[A]</span>
            </div>
          </div>
        </div>

        <div className="stat-card border-l-2 border-l-[#00ff00]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-0">active_delays:</p>
              <p className="text-lg font-mono text-[#00ff00]">{filteredStats.active_delays}</p>
            </div>
            <div className="w-8 h-8 bg-black flex items-center justify-center border border-[#00ff00]">
              <span className="text-xs font-mono text-[#00ff00]">[T]</span>
            </div>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-1">
        <div className="card chart-card p-2">
          <h3 className="text-xs font-mono text-[#00ff00] mb-2 flex items-center space-x-1">
            <span>[*]</span>
            <span>activities_by_status</span>
          </h3>
          {activitiesByStatusData.length > 0 ? (
            <div className="flex items-start gap-4">
              <div className="chart-container">
                <PieChart width={250} height={200}>
                  <Pie
                    data={activitiesByStatusData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                    outerRadius={70}
                    fill="#E55A2B"
                    dataKey="value"
                    stroke="none"
                  >
                    {activitiesByStatusData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="none" className="pie-slice" />
                    ))}
                  </Pie>
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#000000', 
                    border: '1px solid #00ff00',
                    borderRadius: '0',
                    color: '#00ff00',
                    fontFamily: 'Courier New, monospace'
                  }}
                  itemStyle={{ color: '#00ff00' }}
                  labelStyle={{ color: '#00ff00' }}
                />
                </PieChart>
              </div>
              <div className="flex-1 min-w-0">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b border-[#00ff00]">
                      <th className="text-left py-1 text-xs font-mono text-[#00ff00]">status</th>
                      <th className="text-right py-1 text-xs font-mono text-[#00ff00]">count</th>
                      <th className="text-right py-1 text-xs font-mono text-[#00ff00]">%</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#00ff00]">
                    {activitiesByStatusData.map((entry, index) => {
                      const total = activitiesByStatusData.reduce((sum, e) => sum + e.value, 0);
                      const percent = ((entry.value / total) * 100).toFixed(1);
                      return (
                        <tr key={index} className="hover:bg-[#001100]">
                          <td className="py-1 text-[#00ff00]">
                            <div className="flex items-center gap-1">
                              <span className="text-[#00ff00]">[</span>
                              <div 
                                className="w-2 h-2 border border-[#00ff00]" 
                                style={{ backgroundColor: COLORS[index % COLORS.length] }}
                              />
                              <span className="text-[#00ff00]">]</span>
                              <span>{entry.name}</span>
                            </div>
                          </td>
                          <td className="py-1 text-right text-[#00ff00]">{entry.value}</td>
                          <td className="py-1 text-right text-[#00ff00] opacity-70">{percent}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-[#00ff00] opacity-50 text-center py-4 font-mono text-xs">> no data available</p>
          )}
        </div>

        <div className="card chart-card p-2">
          <h3 className="text-xs font-mono text-[#00ff00] mb-2 flex items-center space-x-1">
            <span>[*]</span>
            <span>top_events_by_type</span>
          </h3>
          {eventsByTypeData.length > 0 ? (
            <div className="flex items-start gap-4">
              <div className="chart-container">
                <PieChart width={250} height={200}>
                  <Pie
                    data={eventsByTypeData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                    outerRadius={70}
                    fill="#E55A2B"
                    dataKey="value"
                    stroke="none"
                  >
                    {eventsByTypeData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="none" className="pie-slice" />
                    ))}
                  </Pie>
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#000000', 
                    border: '1px solid #00ff00',
                    borderRadius: '0',
                    color: '#00ff00',
                    fontFamily: 'Courier New, monospace'
                  }}
                  itemStyle={{ color: '#00ff00' }}
                  labelStyle={{ color: '#00ff00' }}
                />
                </PieChart>
              </div>
              <div className="flex-1 min-w-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#2a2a2a]">
                      <th className="text-left py-2 text-xs font-semibold text-gray-300 uppercase tracking-wider">event type</th>
                      <th className="text-right py-2 text-xs font-semibold text-gray-300 uppercase tracking-wider">count</th>
                      <th className="text-right py-2 text-xs font-semibold text-gray-300 uppercase tracking-wider">%</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2a2a2a]">
                    {eventsByTypeData.map((entry, index) => {
                      const total = eventsByTypeData.reduce((sum, e) => sum + e.value, 0);
                      const percent = ((entry.value / total) * 100).toFixed(1);
                      return (
                        <tr key={index} className="hover:bg-[#242424] transition-colors">
                          <td className="py-2 text-gray-200">
                            <div className="flex items-center gap-2">
                              <div 
                                className="w-3 h-3 rounded-sm" 
                                style={{ backgroundColor: COLORS[index % COLORS.length] }}
                              />
                              <span className="truncate">{entry.name}</span>
                            </div>
                          </td>
                          <td className="py-2 text-right text-gray-200 font-medium">{entry.value}</td>
                          <td className="py-2 text-right text-gray-400">{percent}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-[#00ff00] opacity-50 text-center py-4 font-mono text-xs">> no data available</p>
          )}
        </div>
      </div>

      {/* Recent Workflows */}
      <div className="card p-2">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-mono text-[#00ff00] flex items-center space-x-1">
            <span>[W]</span>
            <span>recent_workflows</span>
          </h3>
          <Link
            to="/workflows"
            className="text-xs font-mono text-[#00ff00] hover:text-[#00ffff] border border-[#00ff00] px-1 py-0"
          >
            view_all ->
          </Link>
        </div>
        {workflows.length > 0 ? (
          <div className="overflow-x-auto border border-[#00ff00]">
            <table className="min-w-full divide-y divide-[#00ff00] font-mono text-xs">
              <thead className="bg-black">
                <tr>
                  <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                    workflow_id
                  </th>
                  <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                    type
                  </th>
                  <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                    version
                  </th>
                  <th className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]">
                    updated
                  </th>
                </tr>
              </thead>
              <tbody className="bg-black divide-y divide-[#00ff00]">
                {workflows.map((workflow) => (
                  <tr
                    key={workflow.workflow_id}
                    className="hover:bg-[#001100] cursor-pointer"
                  >
                    <td className="px-2 py-1 whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <Link
                          to={`/workflows/${workflow.workflow_id}`}
                          className="text-xs font-mono text-[#00ff00] hover:text-[#00ffff]"
                        >
                          {workflow.workflow_id.substring(0, 8)}...
                        </Link>
                        <CopyButton text={workflow.workflow_id} />
                      </div>
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap">
                      <span className="inline-flex items-center px-1 py-0 text-xs font-mono bg-black text-[#00ff00] border border-[#00ff00]">
                        {workflow.workflow_type}
                      </span>
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap text-xs font-mono text-[#00ff00]">
                      {workflow.version}
                    </td>
                    <td className="px-2 py-1 whitespace-nowrap text-xs font-mono text-[#00ff00] opacity-70">
                      {workflow.updated_at
                        ? new Date(workflow.updated_at).toLocaleString()
                        : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-4">
            <p className="text-[#00ff00] opacity-50 font-mono text-xs">> no workflows found</p>
          </div>
        )}
      </div>
    </div>
  );
}
