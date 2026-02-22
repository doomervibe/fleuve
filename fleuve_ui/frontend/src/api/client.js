/**
 * API client matching fleuve-go structure.
 * Adapts Python backend endpoints to fleuve-go response shapes.
 * Use VITE_USE_MOCK=true for development without backend.
 */

import { mockApi } from './mock.js';

const useMock = import.meta.env.VITE_USE_MOCK === 'true';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

async function fetchAPI(endpoint) {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }
  return response.json();
}

async function fetchHealth() {
  const base = import.meta.env.VITE_API_URL || '';
  const url = base ? `${base.replace(/\/api\/?$/, '')}/health` : '/health';
  const response = await fetch(url);
  if (!response.ok) throw new Error('Health check failed');
  return response.json();
}

export const api = useMock
  ? mockApi
  : {
  health: () => fetchHealth(),

  stats: async () => {
    const data = await fetchAPI('/stats');
    return data;
  },

  workflows: {
    list: async (params) => {
      const query = new URLSearchParams();
      if (params?.workflow_type) query.set('workflow_type', params.workflow_type);
      if (params?.workflow_id) query.set('search', params.workflow_id);
      if (params?.limit) query.set('limit', params.limit.toString());
      if (params?.offset) query.set('offset', params.offset.toString());
      const data = await fetchAPI(`/workflows?${query}`);
      return { workflows: Array.isArray(data) ? data : data.workflows || [], total: data.total ?? data.length ?? 0 };
    },
    get: async (id) => {
      const [workflow, events, activitiesResp, delaysResp] = await Promise.all([
        fetchAPI(`/workflows/${id}`),
        fetchAPI(`/workflows/${id}/events`),
        fetchAPI(`/workflows/${id}/activities`),
        fetchAPI(`/workflows/${id}/delays`),
      ]);
      const eventsList = Array.isArray(events) ? events : events?.events ?? [];
      const activities = Array.isArray(activitiesResp)
        ? activitiesResp
        : activitiesResp?.activities ?? [];
      const delays = Array.isArray(delaysResp) ? delaysResp : delaysResp?.delays ?? [];
      // Adapt to fleuve-go WorkflowDetail shape
      return {
        workflow_id: workflow.workflow_id,
        workflow_type: workflow.workflow_type,
        event_count: eventsList?.length ?? 0,
        events: eventsList.map((e) => ({
          id: e.global_id,
          workflow_id: e.workflow_id,
          workflow_type: e.workflow_type,
          event_number: e.workflow_version,
          event_type: e.event_type,
          body: e.body || {},
          tags: e.metadata?.tags || e.metadata?.workflow_tags || [],
          created_at: e.at,
        })),
        activities: activities.map((a) => ({
          id: a.workflow_id + '-' + a.event_number,
          workflow_id: a.workflow_id,
          workflow_type: workflow.workflow_type,
          event_number: a.event_number,
          status: a.status,
          checkpoint: a.checkpoint || {},
          retry_count: a.retry_count ?? 0,
          runner_id: a.runner_id,
          resulting_command: null,
          started_at: a.started_at,
          finished_at: a.finished_at,
          last_attempt_at: a.last_attempt_at,
          created_at: a.started_at,
          updated_at: a.finished_at || a.started_at,
        })),
        delays: delays.map((d) => ({
          id: d.workflow_id + '-' + d.event_version,
          workflow_id: d.workflow_id,
          workflow_type: d.workflow_type,
          event_number: d.event_version,
          delay_until: d.delay_until,
          next_command: d.next_command || {},
          created_at: d.created_at,
        })),
        created_at: workflow.created_at,
        updated_at: workflow.updated_at,
      };
    },
  },

  events: {
    list: async (params) => {
      const query = new URLSearchParams();
      if (params?.workflow_type) query.set('workflow_type', params.workflow_type);
      if (params?.workflow_id) query.set('workflow_id', params.workflow_id);
      if (params?.event_type) query.set('event_type', params.event_type);
      if (params?.tag) query.set('tag', params.tag);
      if (params?.limit) query.set('limit', (params.limit || 50).toString());
      if (params?.offset) query.set('offset', (params.offset || 0).toString());
      const data = await fetchAPI(`/events?${query}`);
      const events = Array.isArray(data) ? data : data.events || [];
      const eventTypes = data.event_types ?? [...new Set(events.map((e) => e.event_type))];
      const tags = data.tags ?? [...new Set(events.flatMap((e) => e.metadata?.tags || e.metadata?.workflow_tags || []))];
      return { events, total: data.total ?? events.length, event_types: eventTypes, tags };
    },
  },

  activities: {
    list: async (params) => {
      const query = new URLSearchParams();
      if (params?.workflow_type) query.set('workflow_type', params.workflow_type);
      if (params?.status) query.set('status', params.status);
      if (params?.limit) query.set('limit', (params.limit || 50).toString());
      if (params?.offset) query.set('offset', (params.offset || 0).toString());
      const data = await fetchAPI(`/activities?${query}`);
      const activities = Array.isArray(data) ? data : data.activities || [];
      return { activities, total: data.total ?? activities.length };
    },
  },

  delays: {
    list: async (params) => {
      const query = new URLSearchParams();
      if (params?.workflow_type) query.set('workflow_type', params.workflow_type);
      if (params?.limit) query.set('limit', (params.limit || 50).toString());
      if (params?.offset) query.set('offset', (params.offset || 0).toString());
      const data = await fetchAPI(`/delays?${query}`);
      const delays = Array.isArray(data) ? data : data.delays || [];
      return { delays, total: data.total ?? delays.length };
    },
  },

  runners: {
    list: async () => {
      try {
        const data = await fetchAPI('/runners');
        return { runners: data.runners || [], total: 0 };
      } catch {
        return { runners: [], total: 0 };
      }
    },
  },
};
