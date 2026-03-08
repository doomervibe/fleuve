/** API client for Fleuve Framework UI */

// Set USE_MOCK_DATA to true to use mock data instead of real API calls
// You can also set this via localStorage: localStorage.setItem('USE_MOCK_DATA', 'true')
const USE_MOCK_DATA = 
  import.meta.env.VITE_USE_MOCK_DATA === 'true' || 
  localStorage.getItem('USE_MOCK_DATA') === 'true';

const API_BASE = '/api';

// Import mock data
import {
  mockWorkflowTypes,
  mockWorkflows,
  mockStats,
  getMockWorkflowDetail,
  getMockEvents,
  getMockActivities,
  getMockDelays,
  getMockAllEvents,
  getMockAllActivities,
  getMockAllDelays,
} from './mockData';

// Helper to simulate API delay
function delay(ms = 300) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function normalizeActivity(activity = {}) {
  const checkpoint = activity.checkpoint && typeof activity.checkpoint === 'object'
    ? activity.checkpoint
    : {};
  const fallbackActionType =
    checkpoint.action_type ||
    checkpoint.action ||
    checkpoint.step ||
    checkpoint.operation ||
    'unknown';

  return {
    ...activity,
    checkpoint,
    action_type: activity.action_type || fallbackActionType,
    runner_id: activity.runner_id || null,
  };
}

function normalizeDelay(delayRow = {}) {
  const nextCommand = delayRow.next_command && typeof delayRow.next_command === 'object'
    ? delayRow.next_command
    : {};
  const nextCommandType = delayRow.next_command_type || nextCommand.type || '';
  const fallbackDelayType = nextCommandType || (delayRow.cron_expression ? 'cron' : 'delay');

  return {
    ...delayRow,
    next_command: nextCommand,
    next_command_type: nextCommandType,
    delay_type: delayRow.delay_type || fallbackDelayType,
    delay_id: delayRow.delay_id || `${delayRow.workflow_id || 'wf'}:${delayRow.event_version || 'ev'}:${delayRow.delay_until || 'delay'}`,
  };
}

async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

export const api = {
  // Workflow types
  getWorkflowTypes: async () => {
    if (USE_MOCK_DATA) {
      await delay();
      return mockWorkflowTypes;
    }
    return fetchAPI('/workflow-types');
  },

  // Workflows
  batchCancel: async (workflowIds) => {
    if (USE_MOCK_DATA) {
      await delay();
      return { status: 'ok', cancelled: workflowIds };
    }
    const res = await fetch(`${API_BASE}/workflows/batch/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow_ids: workflowIds }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  batchReplay: async (workflowIds) => {
    if (USE_MOCK_DATA) {
      await delay();
      return { status: 'ok', replayed: workflowIds };
    }
    const res = await fetch(`${API_BASE}/workflows/batch/replay`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow_ids: workflowIds }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  getWorkflows: async (params = {}) => {
    if (USE_MOCK_DATA) {
      await delay();
      let workflows = [...mockWorkflows];
      
      // Apply filters
      if (params.workflow_type) {
        workflows = workflows.filter(w => w.workflow_type === params.workflow_type);
      }
      if (params.search) {
        const searchLower = params.search.toLowerCase();
        workflows = workflows.filter(w =>
          w.workflow_id.toLowerCase().includes(searchLower) ||
          w.workflow_type.toLowerCase().includes(searchLower)
        );
      }
      if (params.created_after) {
        const after = new Date(params.created_after).getTime();
        workflows = workflows.filter(w => new Date(w.created_at).getTime() >= after);
      }
      if (params.created_before) {
        const before = new Date(params.created_before).getTime();
        workflows = workflows.filter(w => new Date(w.created_at).getTime() <= before);
      }
      
      // Apply pagination
      const limit = params.limit || 50;
      const offset = params.offset || 0;
      return workflows.slice(offset, offset + limit);
    }
    
    const query = new URLSearchParams();
    if (params.workflow_type) query.append('workflow_type', params.workflow_type);
    if (params.search) query.append('search', params.search);
    if (params.created_after) query.append('created_after', params.created_after);
    if (params.created_before) query.append('created_before', params.created_before);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    return fetchAPI(`/workflows?${query.toString()}`);
  },

  getWorkflow: async (workflowId) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockWorkflowDetail(workflowId);
    }
    return fetchAPI(`/workflows/${workflowId}`);
  },

  getWorkflowEvents: async (workflowId) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockEvents(workflowId);
    }
    return fetchAPI(`/workflows/${workflowId}/events`);
  },

  getWorkflowStateDiff: async (workflowId, v1, v2) => {
    if (USE_MOCK_DATA) {
      await delay();
      const evs = getMockEvents(workflowId);
      const toState = (v) => ({
        version: v,
        events: evs.filter((e) => e.workflow_version <= v).map((e) => ({
          version: e.workflow_version,
          type: e.event_type,
          body: e.body,
          at: e.at,
        })),
      });
      return {
        workflow_id: workflowId,
        version1: v1,
        version2: v2,
        state_v1: toState(v1),
        state_v2: toState(v2),
      };
    }
    return fetchAPI(`/workflows/${workflowId}/state-diff/${v1}/${v2}`);
  },

  getWorkflowStateAtVersion: async (workflowId, version) => {
    if (USE_MOCK_DATA) {
      await delay();
      const workflow = getMockWorkflowDetail(workflowId);
      return workflow.state;
    }
    return fetchAPI(`/workflows/${workflowId}/state/${version}`);
  },

  getWorkflowActivities: async (workflowId) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockActivities(workflowId).map(normalizeActivity);
    }
    const activities = await fetchAPI(`/workflows/${workflowId}/activities`);
    return activities.map(normalizeActivity);
  },

  getWorkflowDelays: async (workflowId) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockDelays(workflowId).map(normalizeDelay);
    }
    const delays = await fetchAPI(`/workflows/${workflowId}/delays`);
    return delays.map(normalizeDelay);
  },

  // Events
  getEvents: async (params = {}) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockAllEvents(params);
    }
    const query = new URLSearchParams();
    if (params.workflow_type) query.append('workflow_type', params.workflow_type);
    if (params.workflow_id) query.append('workflow_id', params.workflow_id);
    if (params.event_type) query.append('event_type', params.event_type);
    if (params.created_after) query.append('created_after', params.created_after);
    if (params.created_before) query.append('created_before', params.created_before);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    return fetchAPI(`/events?${query.toString()}`);
  },

  getEvent: async (eventId) => {
    if (USE_MOCK_DATA) {
      await delay();
      // Find event in mock data
      const allEvents = getMockAllEvents({ limit: 1000 });
      return allEvents.find(e => e.global_id === parseInt(eventId)) || allEvents[0];
    }
    return fetchAPI(`/events/${eventId}`);
  },

  // Activities
  getActivities: async (params = {}) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockAllActivities(params).map(normalizeActivity);
    }
    const query = new URLSearchParams();
    if (params.workflow_id) query.append('workflow_id', params.workflow_id);
    if (params.status) query.append('status', params.status);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const activities = await fetchAPI(`/activities?${query.toString()}`);
    return activities.map(normalizeActivity);
  },

  // Delays
  getDelays: async (params = {}) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockAllDelays(params).map(normalizeDelay);
    }
    const query = new URLSearchParams();
    if (params.workflow_type) query.append('workflow_type', params.workflow_type);
    if (params.workflow_id) query.append('workflow_id', params.workflow_id);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const delays = await fetchAPI(`/delays?${query.toString()}`);
    return delays.map(normalizeDelay);
  },

  // Statistics
  getStats: async () => {
    if (USE_MOCK_DATA) {
      await delay();
      return mockStats;
    }
    return fetchAPI('/stats');
  },
};

// Export mock mode status for UI indication
export const isMockMode = USE_MOCK_DATA;
