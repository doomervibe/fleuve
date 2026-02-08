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
      
      // Apply pagination
      const limit = params.limit || 50;
      const offset = params.offset || 0;
      return workflows.slice(offset, offset + limit);
    }
    
    const query = new URLSearchParams();
    if (params.workflow_type) query.append('workflow_type', params.workflow_type);
    if (params.search) query.append('search', params.search);
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
      return getMockActivities(workflowId);
    }
    return fetchAPI(`/workflows/${workflowId}/activities`);
  },

  getWorkflowDelays: async (workflowId) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockDelays(workflowId);
    }
    return fetchAPI(`/workflows/${workflowId}/delays`);
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
      return getMockAllActivities(params);
    }
    const query = new URLSearchParams();
    if (params.workflow_id) query.append('workflow_id', params.workflow_id);
    if (params.status) query.append('status', params.status);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    return fetchAPI(`/activities?${query.toString()}`);
  },

  // Delays
  getDelays: async (params = {}) => {
    if (USE_MOCK_DATA) {
      await delay();
      return getMockAllDelays(params);
    }
    const query = new URLSearchParams();
    if (params.workflow_type) query.append('workflow_type', params.workflow_type);
    if (params.workflow_id) query.append('workflow_id', params.workflow_id);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    return fetchAPI(`/delays?${query.toString()}`);
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
