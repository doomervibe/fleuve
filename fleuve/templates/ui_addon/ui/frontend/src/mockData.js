/** Mock data for UI development */

// Generate a random UUID-like string
function generateId() {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

// Generate a date in the past
function pastDate(daysAgo = 0, hoursAgo = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  date.setHours(date.getHours() - hoursAgo);
  return date.toISOString();
}

// Generate a date in the future
function futureDate(daysAhead = 0, hoursAhead = 0) {
  const date = new Date();
  date.setDate(date.getDate() + daysAhead);
  date.setHours(date.getHours() + hoursAhead);
  return date.toISOString();
}

// Mock workflow types
export const mockWorkflowTypes = [
  { workflow_type: 'traffic_fine', workflow_count: 45, event_count: 230, last_event_at: pastDate(0, 2) },
  { workflow_type: 'order_processing', workflow_count: 32, event_count: 180, last_event_at: pastDate(0, 5) },
  { workflow_type: 'payment_workflow', workflow_count: 28, event_count: 145, last_event_at: pastDate(1, 3) },
  { workflow_type: 'document_approval', workflow_count: 15, event_count: 89, last_event_at: pastDate(2, 1) },
];

// Mock workflows
export const mockWorkflows = [
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'traffic_fine',
    version: 5,
    state: { fine_amount: 150, status: 'pending_payment', violation_type: 'speeding' },
    created_at: pastDate(5),
    updated_at: pastDate(0, 2),
    is_completed: false,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'order_processing',
    version: 3,
    state: { order_id: 'ORD-12345', status: 'processing', items: 3 },
    created_at: pastDate(3),
    updated_at: pastDate(0, 1),
    is_completed: false,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'payment_workflow',
    version: 7,
    state: { amount: 299.99, currency: 'USD', status: 'completed' },
    created_at: pastDate(7),
    updated_at: pastDate(1, 3),
    is_completed: true,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'document_approval',
    version: 2,
    state: { document_id: 'DOC-789', status: 'pending_review', reviewer: 'john.doe' },
    created_at: pastDate(2),
    updated_at: pastDate(0, 4),
    is_completed: false,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'traffic_fine',
    version: 4,
    state: { fine_amount: 75, status: 'paid', violation_type: 'parking' },
    created_at: pastDate(10),
    updated_at: pastDate(3, 5),
    is_completed: true,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'order_processing',
    version: 6,
    state: { order_id: 'ORD-67890', status: 'shipped', items: 5 },
    created_at: pastDate(1),
    updated_at: pastDate(0, 6),
    is_completed: false,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'payment_workflow',
    version: 2,
    state: { amount: 149.50, currency: 'USD', status: 'pending' },
    created_at: pastDate(4),
    updated_at: pastDate(0, 3),
    is_completed: false,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'document_approval',
    version: 3,
    state: { document_id: 'DOC-456', status: 'approved', reviewer: 'jane.smith' },
    created_at: pastDate(6),
    updated_at: pastDate(2, 2),
    is_completed: true,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'traffic_fine',
    version: 1,
    state: { fine_amount: 200, status: 'pending_payment', violation_type: 'red_light' },
    created_at: pastDate(0, 8),
    updated_at: pastDate(0, 1),
    is_completed: false,
  },
  {
    workflow_id: 'wf_' + generateId(),
    workflow_type: 'order_processing',
    version: 4,
    state: { order_id: 'ORD-11111', status: 'pending', items: 2 },
    created_at: pastDate(0, 12),
    updated_at: pastDate(0, 10),
    is_completed: false,
  },
];

// Mock stats
export const mockStats = {
  total_workflows: 120,
  workflows_by_type: {
    traffic_fine: 45,
    order_processing: 32,
    payment_workflow: 28,
    document_approval: 15,
  },
  workflows_by_state: {
    active: 85,
    completed: 30,
    pending: 5,
  },
  total_events: 644,
  events_by_type: {
    'traffic_fine.violation_created': 45,
    'traffic_fine.payment_received': 30,
    'order_processing.order_placed': 32,
    'order_processing.order_shipped': 25,
    'payment_workflow.payment_initiated': 28,
    'payment_workflow.payment_completed': 22,
    'document_approval.document_submitted': 15,
    'document_approval.document_approved': 12,
    'workflow.completed': 35,
    'workflow.started': 120,
  },
  total_activities: 180,
  activities_by_status: {
    completed: 120,
    pending: 35,
    running: 15,
    failed: 8,
    retrying: 2,
  },
  pending_activities: 35,
  failed_activities: 8,
  total_delays: 25,
  active_delays: 12,
};

// Mock workflow detail
export function getMockWorkflowDetail(workflowId) {
  const workflow = mockWorkflows.find(w => w.workflow_id === workflowId) || mockWorkflows[0];
  return {
    ...workflow,
    subscriptions: [
      { event_type: 'payment_received', handler: 'process_payment' },
      { event_type: 'workflow.completed', handler: 'cleanup' },
    ],
  };
}

// Mock events
export function getMockEvents(workflowId) {
  return [
    {
      global_id: 1,
      workflow_id: workflowId,
      workflow_type: 'traffic_fine',
      workflow_version: 1,
      event_type: 'traffic_fine.violation_created',
      body: { fine_amount: 150, violation_type: 'speeding' },
      at: pastDate(5),
      metadata: { source: 'camera_system' },
    },
    {
      global_id: 2,
      workflow_id: workflowId,
      workflow_type: 'traffic_fine',
      workflow_version: 2,
      event_type: 'traffic_fine.notification_sent',
      body: { notification_type: 'email', recipient: 'driver@example.com' },
      at: pastDate(4, 12),
      metadata: {},
    },
    {
      global_id: 3,
      workflow_id: workflowId,
      workflow_type: 'traffic_fine',
      workflow_version: 3,
      event_type: 'traffic_fine.payment_received',
      body: { amount: 150, payment_method: 'credit_card' },
      at: pastDate(2, 6),
      metadata: { payment_id: 'pay_123' },
    },
    {
      global_id: 4,
      workflow_id: workflowId,
      workflow_type: 'traffic_fine',
      workflow_version: 4,
      event_type: 'workflow.completed',
      body: { status: 'completed' },
      at: pastDate(1, 3),
      metadata: {},
    },
  ];
}

// Mock activities
export function getMockActivities(workflowId) {
  return [
    {
      workflow_id: workflowId,
      event_number: 1,
      status: 'completed',
      started_at: pastDate(5, 1),
      finished_at: pastDate(5, 0.5),
      last_attempt_at: pastDate(5, 0.5),
      retry_count: 0,
      max_retries: 3,
      error_message: null,
      error_type: null,
      checkpoint: { step: 'process_violation' },
    },
    {
      workflow_id: workflowId,
      event_number: 2,
      status: 'completed',
      started_at: pastDate(4, 12),
      finished_at: pastDate(4, 11.5),
      last_attempt_at: pastDate(4, 11.5),
      retry_count: 0,
      max_retries: 3,
      error_message: null,
      error_type: null,
      checkpoint: { step: 'send_notification' },
    },
    {
      workflow_id: workflowId,
      event_number: 3,
      status: 'running',
      started_at: pastDate(2, 6),
      finished_at: null,
      last_attempt_at: pastDate(2, 6),
      retry_count: 0,
      max_retries: 3,
      error_message: null,
      error_type: null,
      checkpoint: { step: 'process_payment' },
    },
    {
      workflow_id: workflowId,
      event_number: 4,
      status: 'pending',
      started_at: pastDate(1, 3),
      finished_at: null,
      last_attempt_at: null,
      retry_count: 0,
      max_retries: 3,
      error_message: null,
      error_type: null,
      checkpoint: {},
    },
  ];
}

// Helper to generate next N cron fire times (simplified for mock)
function mockNextFireTimes(baseDate, count = 5) {
  const result = [];
  const d = new Date(baseDate);
  for (let i = 0; i < count; i++) {
    d.setHours(d.getHours() + 24);
    result.push(d.toISOString());
  }
  return result;
}

// Mock delays
export function getMockDelays(workflowId) {
  const now = new Date();
  const nextDay = new Date(now);
  nextDay.setDate(nextDay.getDate() + 1);
  nextDay.setHours(9, 0, 0, 0);
  return [
    {
      workflow_id: workflowId,
      workflow_type: 'traffic_fine',
      delay_until: futureDate(2, 0),
      event_version: 3,
      created_at: pastDate(2, 6),
      next_command: { type: 'check_payment_status', params: {} },
    },
    {
      workflow_id: workflowId,
      workflow_type: 'traffic_fine',
      delay_until: nextDay.toISOString(),
      event_version: 4,
      created_at: pastDate(1, 3),
      next_command: { type: 'cron_tick', params: {} },
      cron_expression: '0 9 * * *',
      cron_timezone: 'UTC',
      next_fire_times: mockNextFireTimes(nextDay, 5),
    },
  ];
}

// Mock all events
export function getMockAllEvents(params = {}) {
  let events = [];
  
  mockWorkflows.forEach((wf, idx) => {
    const workflowEvents = getMockEvents(wf.workflow_id);
    events.push(...workflowEvents);
  });
  
  // Apply filters
  if (params.workflow_type) {
    events = events.filter(e => e.workflow_type === params.workflow_type);
  }
  if (params.workflow_id) {
    events = events.filter(e => e.workflow_id === params.workflow_id);
  }
  if (params.event_type) {
    events = events.filter(e => e.event_type === params.event_type);
  }
  if (params.created_after) {
    const after = new Date(params.created_after).getTime();
    events = events.filter(e => new Date(e.at).getTime() >= after);
  }
  if (params.created_before) {
    const before = new Date(params.created_before).getTime();
    events = events.filter(e => new Date(e.at).getTime() <= before);
  }

  // Apply pagination
  const limit = params.limit || 50;
  const offset = params.offset || 0;
  return events.slice(offset, offset + limit);
}

// Mock all activities
export function getMockAllActivities(params = {}) {
  let activities = [];
  
  mockWorkflows.forEach((wf) => {
    const workflowActivities = getMockActivities(wf.workflow_id);
    activities.push(...workflowActivities);
  });
  
  // Apply filters
  if (params.workflow_id) {
    activities = activities.filter(a => a.workflow_id === params.workflow_id);
  }
  if (params.status) {
    activities = activities.filter(a => a.status === params.status);
  }
  
  // Apply pagination
  const limit = params.limit || 50;
  const offset = params.offset || 0;
  return activities.slice(offset, offset + limit);
}

// Mock all delays
export function getMockAllDelays(params = {}) {
  let delays = [];
  
  mockWorkflows.forEach((wf) => {
    const workflowDelays = getMockDelays(wf.workflow_id);
    delays.push(...workflowDelays);
  });
  
  // Apply filters
  if (params.workflow_type) {
    delays = delays.filter(d => d.workflow_type === params.workflow_type);
  }
  if (params.workflow_id) {
    delays = delays.filter(d => d.workflow_id === params.workflow_id);
  }
  
  // Apply pagination
  const limit = params.limit || 50;
  const offset = params.offset || 0;
  return delays.slice(offset, offset + limit);
}
