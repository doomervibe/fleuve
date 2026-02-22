/**
 * Mock API for frontend development without backend.
 * Provides rich sample data for all UI components.
 */

const WORKFLOW_TYPES = [
  'order_fulfillment',
  'payment_processing',
  'inventory_sync',
  'user_onboarding',
  'subscription_renewal',
  'refund_workflow',
  'shipping_tracking',
  'notification_dispatch',
];

const EVENT_TYPES = [
  'OrderCreated',
  'PaymentReceived',
  'ItemShipped',
  'UserSignedUp',
  'SubscriptionRenewed',
  'RefundRequested',
  'InventoryUpdated',
  'NotificationSent',
  'WorkflowStarted',
  'StepCompleted',
];

const TAGS = [
  'urgent',
  'vip',
  'retry',
  'batch',
  'priority',
  'test',
  'production',
  'staging',
  'manual',
  'automated',
];

function addDays(d, days) {
  const out = new Date(d);
  out.setDate(out.getDate() + days);
  return out.toISOString();
}

function addHours(d, h) {
  const out = new Date(d);
  out.setHours(out.getHours() + h);
  return out.toISOString();
}

function addMinutes(d, m) {
  const out = new Date(d);
  out.setMinutes(out.getMinutes() + m);
  return out.toISOString();
}

function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randomItems(arr, min = 0, max = 3) {
  const n = Math.floor(Math.random() * (max - min + 1)) + min;
  const shuffled = [...arr].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, n);
}

const now = new Date();

// Generate 40 workflows
const MOCK_WORKFLOWS = Array.from({ length: 40 }, (_, i) => {
  const id = `wf-${String(1000 + i).padStart(6, '0')}`;
  const type = randomItem(WORKFLOW_TYPES);
  const updated = addDays(now, -Math.floor(Math.random() * 14));
  return {
    workflow_id: id,
    workflow_type: type,
    version: Math.floor(Math.random() * 50) + 1,
    created_at: addDays(now, -30),
    updated_at: updated,
  };
});

// Generate 120 events across workflows
const MOCK_EVENTS = [];
MOCK_WORKFLOWS.forEach((w, wi) => {
  const count = Math.floor(Math.random() * 10) + 3;
  for (let i = 0; i < count; i++) {
    const eventType = randomItem(EVENT_TYPES);
    const tags = randomItems(TAGS, 0, 3);
    MOCK_EVENTS.push({
      global_id: `ev-${w.workflow_id}-${i}`,
      workflow_id: w.workflow_id,
      workflow_type: w.workflow_type,
      workflow_version: i + 1,
      event_type: eventType,
      body: {
        type: eventType,
        payload: { id: i, data: `event-${i}-data` },
        metadata: { source: 'mock' },
      },
      metadata: { tags, workflow_tags: tags },
      tags,
      at: addMinutes(new Date(w.updated_at), -i * 5),
      created_at: addMinutes(new Date(w.updated_at), -i * 5),
    });
  }
});

// Generate runner names for mock
const MOCK_RUNNER_NAMES = [
  'order_fulfillment_runner',
  'payment_processing_runner',
  'inventory_sync_runner',
  'user_onboarding_runner',
  'subscription_renewal_runner',
  'refund_workflow_runner',
  'shipping_tracking_runner',
  'notification_dispatch_runner',
];

// Generate 90 activities
const MOCK_ACTIVITIES = [];
const STATUSES = ['pending', 'running', 'completed', 'failed', 'retrying'];
MOCK_WORKFLOWS.slice(0, 25).forEach((w) => {
  const count = Math.floor(Math.random() * 8) + 2;
  const runnerId = randomItem(MOCK_RUNNER_NAMES);
  for (let i = 0; i < count; i++) {
    const status = randomItem(STATUSES);
    MOCK_ACTIVITIES.push({
      workflow_id: w.workflow_id,
      workflow_type: w.workflow_type,
      event_number: i + 1,
      status,
      runner_id: status !== 'pending' ? runnerId : null,
      retry_count: status === 'retrying' ? Math.floor(Math.random() * 3) + 1 : 0,
      started_at: addHours(now, -i * 2),
      finished_at: status !== 'pending' && status !== 'running' ? addHours(now, -i * 2 + 1) : null,
      last_attempt_at: addHours(now, -i),
    });
  }
});

// Generate 55 delays
const MOCK_DELAYS = [];
MOCK_WORKFLOWS.slice(0, 20).forEach((w, wi) => {
  const count = Math.floor(Math.random() * 5) + 1;
  for (let i = 0; i < count; i++) {
    const delayUntil = addHours(now, Math.floor(Math.random() * 72) + 1);
    MOCK_DELAYS.push({
      id: `delay-${w.workflow_id}-${i}`,
      workflow_id: w.workflow_id,
      workflow_type: w.workflow_type,
      event_version: i + 1,
      event_number: i + 1,
      delay_until: delayUntil,
      next_command: {
        type: 'ContinueWorkflow',
        payload: { step: i + 1 },
      },
      created_at: addHours(now, -1),
    });
  }
});

// Generate 24 runners (8 types × 3 partitions or single)
const MOCK_RUNNERS = WORKFLOW_TYPES.slice(0, 8).flatMap((wt, i) => {
  const partitions = i % 3 === 0 ? [0, 1, 2] : [null];
  return partitions.map((p) => ({
    reader_name: `runner-${wt}-${p ?? 'single'}`,
    workflow_type: wt,
    partition_id: p,
    last_event_id: Math.floor(Math.random() * 10000),
    max_event_id: Math.floor(Math.random() * 10000) + 1000,
    lag: Math.floor(Math.random() * 150),
    updated_at: addMinutes(now, -Math.floor(Math.random() * 10)),
  }));
});

function delay(ms = 100) {
  return new Promise((r) => setTimeout(r, ms));
}

export const mockApi = {
  health: async () => {
    await delay(50);
    return { status: 'ok' };
  },

  stats: async () => {
    await delay(80);
    const pending = MOCK_ACTIVITIES.filter((a) => a.status === 'pending').length;
    const failed = MOCK_ACTIVITIES.filter((a) => a.status === 'failed').length;
    const now = new Date();
    const activeDelays = MOCK_DELAYS.filter((d) => new Date(d.delay_until) > now).length;
    return {
      total_workflows: MOCK_WORKFLOWS.length,
      workflows_by_type: {},
      workflows_by_state: {},
      total_events: MOCK_EVENTS.length,
      events_by_type: {},
      total_activities: MOCK_ACTIVITIES.length,
      activities_by_status: {},
      pending_activities: pending,
      failed_activities: failed,
      total_delays: MOCK_DELAYS.length,
      active_delays: activeDelays,
    };
  },

  workflows: {
    list: async (params) => {
      await delay(150);
      let workflows = [...MOCK_WORKFLOWS];
      if (params?.workflow_type) {
        workflows = workflows.filter((w) => w.workflow_type === params.workflow_type);
      }
      if (params?.workflow_id || params?.search) {
        const q = (params.workflow_id || params.search || '').toLowerCase();
        workflows = workflows.filter((w) => w.workflow_id.toLowerCase().includes(q));
      }
      const total = workflows.length;
      const offset = Math.max(0, parseInt(params?.offset, 10) || 0);
      const limit = Math.max(1, Math.min(100, parseInt(params?.limit, 10) || 50));
      workflows = workflows.slice(offset, offset + limit);
      // Add runner_id from most recent activity per workflow
      const workflowsWithRunner = workflows.map((w) => {
        const act = MOCK_ACTIVITIES
          .filter((a) => a.workflow_id === w.workflow_id && a.runner_id)
          .sort((a, b) => new Date(b.started_at) - new Date(a.started_at))[0];
        return { ...w, runner_id: act?.runner_id ?? null };
      });
      return { workflows: workflowsWithRunner, total };
    },

    get: async (id) => {
      await delay(200);
      const workflow = MOCK_WORKFLOWS.find((w) => w.workflow_id === id);
      if (!workflow) throw new Error('Workflow not found');

      const events = MOCK_EVENTS.filter((e) => e.workflow_id === id).map((e) => ({
        id: e.global_id,
        workflow_id: e.workflow_id,
        workflow_type: e.workflow_type,
        event_number: e.workflow_version,
        body: e.body || {},
        tags: e.metadata?.tags || e.metadata?.workflow_tags || e.tags || [],
        created_at: e.at,
      }));

      const activities = MOCK_ACTIVITIES.filter((a) => a.workflow_id === id).map((a) => ({
        id: a.workflow_id + '-' + a.event_number,
        workflow_id: a.workflow_id,
        workflow_type: workflow.workflow_type,
        event_number: a.event_number,
        status: a.status,
        runner_id: a.runner_id ?? null,
        checkpoint: {},
        retry_count: a.retry_count ?? 0,
        resulting_command: a.status === 'completed' ? { type: 'Success', result: {} } : null,
        created_at: a.started_at,
        updated_at: a.finished_at || a.started_at,
      }));

      const delays = MOCK_DELAYS.filter((d) => d.workflow_id === id).map((d) => ({
        id: d.workflow_id + '-' + d.event_version,
        workflow_id: d.workflow_id,
        workflow_type: d.workflow_type,
        event_number: d.event_version,
        delay_until: d.delay_until,
        next_command: d.next_command || {},
        created_at: d.created_at,
      }));

      return {
        workflow_id: workflow.workflow_id,
        workflow_type: workflow.workflow_type,
        event_count: events.length,
        events,
        activities,
        delays,
        created_at: workflow.created_at,
        updated_at: workflow.updated_at,
      };
    },
  },

  events: {
    list: async (params) => {
      await delay(150);
      let events = [...MOCK_EVENTS];
      if (params?.event_type) {
        events = events.filter((e) => e.event_type === params.event_type);
      }
      if (params?.workflow_id) {
        events = events.filter((e) => e.workflow_id === params.workflow_id);
      }
      if (params?.tag) {
        const tags = params.tag;
        events = events.filter((e) => {
          const t = e.metadata?.tags || e.metadata?.workflow_tags || e.tags || [];
          return t.includes(tags);
        });
      }
      const total = events.length;
      const offset = Math.max(0, parseInt(params?.offset, 10) || 0);
      const limit = Math.max(1, Math.min(200, parseInt(params?.limit, 10) || 100));
      const eventTypes = [...new Set(events.map((e) => e.event_type))];
      const tags = [...new Set(events.flatMap((e) => e.metadata?.tags || e.metadata?.workflow_tags || e.tags || []))];
      events = events.slice(offset, offset + limit);
      return { events, total, event_types: eventTypes, tags };
    },
  },

  activities: {
    list: async (params) => {
      await delay(150);
      let activities = [...MOCK_ACTIVITIES];
      if (params?.status) {
        activities = activities.filter((a) => a.status === params.status);
      }
      if (params?.workflow_type) {
        activities = activities.filter((a) => a.workflow_type === params.workflow_type);
      }
      const total = activities.length;
      const offset = Math.max(0, parseInt(params?.offset, 10) || 0);
      const limit = Math.max(1, Math.min(100, parseInt(params?.limit, 10) || 50));
      activities = activities.slice(offset, offset + limit);
      return { activities, total };
    },
  },

  delays: {
    list: async (params) => {
      await delay(150);
      let delays = [...MOCK_DELAYS];
      if (params?.workflow_type) {
        delays = delays.filter((d) => d.workflow_type === params.workflow_type);
      }
      const total = delays.length;
      const offset = Math.max(0, parseInt(params?.offset, 10) || 0);
      const limit = Math.max(1, Math.min(100, parseInt(params?.limit, 10) || 50));
      delays = delays.slice(offset, offset + limit);
      return { delays, total };
    },
  },

  runners: {
    list: async (params) => {
      await delay(100);
      let runners = [...MOCK_RUNNERS];
      if (params?.workflow_type) {
        runners = runners.filter((r) => r.workflow_type === params.workflow_type);
      }
      return { runners, total: runners.length };
    },
  },
};
