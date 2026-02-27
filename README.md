<div class="title-block" style="text-align: center;" align="center">
  <h1>Fleuve - Workflow Framework for Python</h1>
  <img width="124" height="118" alt="image" src="https://github.com/user-attachments/assets/2faa70b2-6eef-4323-9b4b-13a2321bbdf8" />
  <p>
      <b>Fleuve</b> (French for "river") is a type-safe, production-ready workflow framework for Python that enables durable workflow execution, reliable state management, and scalable event-driven applications. Build long-running business processes with automatic retries, checkpoint/resume, and horizontal scaling.
  </p>

</div>



## Why Fleuve? (vs Temporal)

If you're considering [Temporal](https://temporal.io/) or similar workflow engines, here's how Fleuve differs:

| | Fleuve | Temporal |
|---|---|---|
| **Architecture** | Event sourcing: events are the source of truth | Activity-based: state derived from activity execution |
| **Infrastructure** | PostgreSQL + NATS (add to your existing stack) | Dedicated Temporal server or Temporal Cloud |
| **Deployment** | Run as a Python app; no separate workflow service | Requires Temporal server(s) or managed cloud |
| **Data ownership** | Events stored in your PostgreSQL; full SQL access | State in Temporal's storage; export for analytics |
| **Event history** | Complete audit trail; time-travel debugging; replay at any version | History available via API |
| **Type safety** | Pydantic-first; full mypy support | SDK types; less integrated with Python typing |
| **Schema evolution** | Built-in `upcast()` for event schema migration | Versioning APIs |
| **Cron / recurring** | Native cron expressions in delays | Workflow schedules |
| **License** | MIT | Apache 2.0 (server) / proprietary (Cloud) |

**Choose Fleuve when** you want event sourcing, own your data in PostgreSQL, prefer a lighter deployment (no dedicated workflow server), or need tight Python/Pydantic integration. **Choose Temporal when** you need multi-language workers, a managed cloud offering, or Temporal's broader ecosystem.

## Table of Contents

- [Why Fleuve? (vs Temporal)](#why-fleuve-vs-temporal)
- [Quick Start](#quick-start)
- [Features](#features)
- [Installation](#installation)
- [Core Concepts](#core-concepts)
- [Usage Examples](#usage-examples)
- [Architecture](#architecture)
- [Advanced Features](#advanced-features)
- [Horizontal Scaling](#horizontal-scaling)
- [API Reference](#api-reference)
- [Production Deployment](#production-deployment)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Resources](#resources)

## Quick Start

Get started with Fleuve in minutes. Here's a minimal workflow example:

```python
from typing import Literal
from pydantic import BaseModel
from fleuve import Workflow, EventBase, StateBase, Rejection
from fleuve.setup import create_workflow_runner

# 1. Define Events (workflow state changes)
class EvCounterIncremented(EventBase):
    type: Literal["counter.incremented"] = "counter.incremented"
    amount: int

# 2. Define Commands (workflow inputs)
class CmdIncrementCounter(BaseModel):
    amount: int

# 3. Define State (workflow state)
class CounterState(StateBase):
    count: int = 0
    subscriptions: list = []

# 4. Define Workflow (business logic)
class CounterWorkflow(Workflow[EvCounterIncremented, CmdIncrementCounter, CounterState, EvCounterIncremented]):
    @classmethod
    def name(cls) -> str:
        return "counter"
    
    @staticmethod
    def decide(state: CounterState | None, cmd: CmdIncrementCounter) -> list[EvCounterIncremented] | Rejection:
        if cmd.amount < 0:
            return Rejection(msg="Amount must be positive")
        return [EvCounterIncremented(amount=cmd.amount)]
    
    @staticmethod
    def _evolve(state: CounterState | None, event: EvCounterIncremented) -> CounterState:
        if state is None:
            state = CounterState(subscriptions=[])
        state.count += event.amount
        return state
    
    @classmethod
    def event_to_cmd(cls, e: EvCounterIncremented) -> CmdIncrementCounter | None:
        return None
    
    @staticmethod
    def is_final_event(e: EvCounterIncremented) -> bool:
        return False

# 5. Run your workflow (minimal setup!)
async def main():
    async with create_workflow_runner(
        workflow_type=CounterWorkflow,
        state_type=CounterState,
    ) as resources:
        repo = resources.repo
        runner = resources.runner
        
        # Create a workflow instance
        result = await repo.create_new(
            cmd=CmdIncrementCounter(amount=5),
            workflow_id="counter-1"
        )
        print(f"Counter value: {result.state.count}")
        
        # Process more commands
        await repo.process_command("counter-1", CmdIncrementCounter(amount=3))
        
        # Run the workflow runner to process events
        await runner.run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

That's it! Fleuve handles database setup, state caching, event persistence, and workflow execution automatically.

See the [Step-by-Step Tutorial](#step-by-step-tutorial) for a complete working example.

## Features

### Durable Workflows
- **Long-running processes**: Build workflows that run for hours, days, or weeks
- **Automatic persistence**: All workflow state changes are automatically persisted
- **Complete history**: Full audit trail of all workflow events
- **Time-travel debugging**: Reconstruct workflow state at any point in time
- **Encrypted storage**: Optional encryption for sensitive workflow data

### Activities & Side Effects
- **Declarative actions**: Handle side effects via adapters (send emails, call APIs, etc.)
- **Automatic retries**: Built-in retry logic with exponential backoff
- **Checkpoint/resume**: Save progress in long-running activities and resume on failure
- **Idempotency**: Automatic idempotency guarantees for safe retries
- **Recovery**: Automatic recovery from interrupted activities

### Signals & Queries
- **Commands**: Send commands to workflows to trigger state changes
- **State queries**: Query current workflow state efficiently
- **Cross-workflow communication**: Workflows can subscribe to events from other workflows
- **Direct messages**: Send events directly to specific workflows

### Retry Policies
- **Configurable retries**: Customize retry behavior per activity
- **Exponential backoff**: Automatic backoff with configurable parameters
- **Max retries**: Set maximum retry attempts
- **Jitter**: Add randomness to prevent thundering herd problems

### Delays & Scheduling
- **Time-based delays**: Schedule workflow steps to execute at specific times
- **Cron schedules**: Recurring delays via cron expressions (e.g. `0 9 * * *` for daily at 9am) with timezone support
- **Resume events**: Automatically resume workflows after delays
- **Long-running workflows**: Support for workflows that span days or weeks

### Horizontal Scaling
- **Hash-based partitioning**: Distribute workflows across multiple workers
- **Zero-downtime scaling**: Scale up or down without stopping workflows
- **Automatic rebalancing**: Redistribute workflows when scaling
- **Multiple workers**: Run multiple worker instances per partition

### Type Safety
- **Full type hints**: Built on Pydantic with complete type annotations
- **Compile-time checking**: Use mypy for static type checking
- **Runtime validation**: Automatic validation of all data structures
- **Self-documenting APIs**: Type hints serve as documentation

### PostgreSQL Backend
- **Durable storage**: All events stored in PostgreSQL
- **Global ordering**: Events have global sequence numbers
- **Standard SQL**: Use familiar SQL tools and queries
- **Encryption support**: Optional encryption at rest

### NATS Integration
- **Fast state access**: Ephemeral state caching in NATS Key-Value store
- **Low latency**: Access workflow state without database queries
- **Automatic invalidation**: Cache automatically invalidated on updates

### Command Gateway
- **HTTP API**: Expose workflow commands via REST for non-Python clients
- **Command parsing**: Registry maps `(command_type, payload)` to typed commands per workflow
- **Lifecycle endpoints**: Pause, resume, and cancel workflows via HTTP
- **Retry failed actions**: POST endpoint to retry failed activities from the dead letter queue

### Lifecycle Management
- **Pause/Resume/Cancel**: System events (`EvSystemPause`, `EvSystemResume`, `EvSystemCancel`) control workflow lifecycle
- **State lifecycle field**: `StateBase.lifecycle` tracks `active`, `paused`, or `cancelled`
- **Guarded processing**: Commands rejected for paused or cancelled workflows

### Snapshots & Event Truncation
- **Automatic snapshots**: Periodic state snapshots at configurable intervals (e.g., every N events)
- **Faster state load**: `load_state` uses snapshots to skip replaying old events; after truncation, state is reconstructed from the snapshot when no events remain
- **Event truncation**: Background service safely deletes events covered by snapshots
- **Retention controls**: Min retention period, reader offset awareness, batch limits

### Dead Letter Queue
- **Failed action tracking**: Activities that exceed retries are tracked as failed
- **Retry endpoint**: Manually retry failed actions via Command Gateway or `ActionExecutor.retry_failed_action`
- **Optional callback**: `on_action_failed` for custom handling (alerts, DLQ routing)

### OpenTelemetry Tracing
- **Optional tracing**: Instrument `process_command`, `load_state`, `execute_action`, and Readers
- **FleuveTracer**: Lightweight tracer with span creation; no-op when OTEL not installed
- **Observability**: Integrate with Jaeger, Zipkin, or any OTLP-compatible backend

### Event Replay & Simulate
- **State reconstruction**: Rebuild workflow state from events at any version (time travel)
- **Replay endpoint**: POST to replay events and get resulting state
- **Simulate (what-if)**: Apply hypothetical commands without persisting; useful for validation

## Installation

### Requirements

- **Python 3.13+**
- **PostgreSQL 12+** (for event storage)
- **NATS Server 2.9+** with JetStream (for ephemeral state caching; use `nats -js`)

### Using pip

```bash
pip install fleuve
```

### Using Poetry (Recommended)

```bash
poetry add fleuve
```

### Development Installation

```bash
git clone https://github.com/doomervibe/fleuve.git
cd fleuve
poetry install
```

### Setting Up Infrastructure

#### PostgreSQL

```bash
# Using Docker
docker run -d \
  --name fleuve-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16

# Create database
psql -h localhost -U postgres -c "CREATE DATABASE fleuve;"
```

#### NATS Server (JetStream required)

Fleuve uses NATS Key-Value for ephemeral state caching and requires JetStream. Start NATS with the `-js` flag:

```bash
# Using Docker
docker run -d \
  --name fleuve-nats \
  -p 4222:4222 \
  -p 8222:8222 \
  nats:latest \
  -js
```


## Core Concepts

Understanding these core concepts is essential to working with Fleuve:

### 1. Workflows

**Workflows** are the primary abstraction in Fleuve. They represent long-running business processes that can span seconds, hours, days, or weeks. Workflows are durable, meaning they survive process restarts and failures.

**Key Properties:**
- **Durable execution**: Workflows continue running even if workers restart
- **State management**: Workflow state is automatically managed and persisted
- **Pure business logic**: Workflow logic is deterministic and testable
- **Type-safe**: Full type hints ensure correctness at compile time

**Workflow Methods:**
- `decide(state, cmd)`: Process commands and emit events (pure function). Emit `EvSubscriptionAdded`, `EvSubscriptionRemoved`, etc. to manage subscriptions; emit `EvScheduleAdded`, `EvScheduleRemoved` for cron schedules.
- `_evolve(state, event)`: Derive new state from events (pure function). You implement this; `evolve()` orchestrates system events (lifecycle, sync) and delegates to `_evolve` for domain events.
- `event_to_cmd(event)`: Convert external events to commands
- `is_final_event(event)`: Determine when workflow is complete

### 2. Events

**Events** are immutable records of workflow state changes. They represent **facts** that have happened in your workflow. Events are stored permanently and can be replayed to reconstruct workflow state.

**Key Properties:**
- Events are **immutable** - once created, they cannot be changed
- Events are **stored permanently** in PostgreSQL
- Events have a **type** field that uniquely identifies the event kind
- Events are **ordered** by a global sequence number

**Example:**

```python
from fleuve.model import EventBase
from typing import Literal

class EvOrderPlaced(EventBase):
    type: Literal["order.placed"] = "order.placed"
    order_id: str
    customer_id: str
    total: float
    
class EvOrderShipped(EventBase):
    type: Literal["order.shipped"] = "order.shipped"
    order_id: str
    tracking_number: str
```

**Best Practices:**
- Use past tense for event names (e.g., "OrderPlaced" not "PlaceOrder")
- Include all relevant data in the event (events should be self-contained)
- Never modify events after they're created
- Use Literal types for the `type` field

### 3. Commands

**Commands** are inputs to workflows. They represent **intentions** or **requests** to change workflow state. Commands are validated by the workflow and can be rejected if business rules are violated.

**Key Properties:**
- Commands are **validated** by the workflow's `decide` method
- Commands can be **rejected** if business rules are violated
- Commands are **not stored** (only the resulting events are stored)
- Commands trigger the creation of events in workflows

**Example:**

```python
from pydantic import BaseModel, Field

class CmdPlaceOrder(BaseModel):
    order_id: str
    customer_id: str
    items: list[str]
    total: float = Field(gt=0)  # Validation: must be positive
    
class CmdShipOrder(BaseModel):
    order_id: str
    tracking_number: str
```

**Best Practices:**
- Use imperative names for commands (e.g., "PlaceOrder")
- Include validation rules using Pydantic
- Keep commands focused on a single action
- Commands should contain all information needed for the decision

### 4. State

**State** represents the current state of a workflow. It is derived by applying events in sequence using the `evolve` method. State is **ephemeral** and can always be reconstructed from events.

**Key Properties:**
- State is **derived** from events using the `evolve` method (pure function)
- State is **cached** in NATS for fast access
- State can be **reconstructed** from events at any point in time
- State includes a `subscriptions` field for cross-workflow communication

**Example:**

```python
from fleuve.model import StateBase

class OrderState(StateBase):
    order_id: str | None = None
    customer_id: str | None = None
    items: list[str] = []
    total: float = 0.0
    status: str = "pending"  # pending, shipped, delivered
    tracking_number: str | None = None
    subscriptions: list = []  # Required field
```

**Best Practices:**
- State should be derivable purely from events
- Use default values for all fields
- Don't store things that can be computed from events
- Keep state simple and focused

### 5. Activities & Adapters

**Activities** (implemented via **Adapters**) handle side effects in workflows. They execute actions like sending emails, calling APIs, or updating external systems. Activities have automatic retry logic and checkpoint/resume support.

**Key Properties:**
- **Declarative**: Define which events trigger activities
- **Automatic retries**: Built-in retry with exponential backoff
- **Checkpoint/resume**: Save progress and resume on failure
- **Idempotent**: Safe to retry automatically

**Adapter Methods:**

#### `act_on(event, context?)` — async generator yielding commands, checkpoints, and/or timeouts
Execute an action for an event; yields zero or more **commands** (each is applied to the same workflow), **CheckpointYield** (checkpoint data), and/or **ActionTimeout** (time limit for the remainder of the action). For checkpoints: `CheckpointYield(data=..., save_now=False)` merges data and persists at end of action; `CheckpointYield(data=..., save_now=True)` merges and persists immediately. For timeouts: `yield ActionTimeout(seconds=30.0)` applies `asyncio.wait_for` to the rest of the action; if it does not complete within the given seconds, `TimeoutError` is raised and the action fails (subject to retries).

```python
@staticmethod
def decide(state: OrderState | None, cmd: CmdPlaceOrder) -> list[EvOrderPlaced] | Rejection:
    # Check if order already exists
    if state is not None:
        return Rejection(msg="Order already exists")
    
    # Validate business rules
    if cmd.total < 10:
        return Rejection(msg="Minimum order amount is $10")
    
    # Emit event
    return [EvOrderPlaced(
        order_id=cmd.order_id,
        customer_id=cmd.customer_id,
        total=cmd.total
    )]
```

**Key Points:**
- `decide` is a **pure function** (no side effects)
- Returns either events or a `Rejection`
- Should validate all business rules
- Can emit multiple events

#### `_evolve(state, event) -> State`
You implement `_evolve` to apply domain events to state. The framework's `evolve()` orchestrates system events (lifecycle, subscriptions, schedules) and delegates to your `_evolve` for domain events.

```python
@staticmethod
def _evolve(state: OrderState | None, event: EvOrderPlaced | EvOrderShipped) -> OrderState:
    # Initialize state if needed
    if state is None:
        state = OrderState(subscriptions=[])
    
    # Apply event
    if isinstance(event, EvOrderPlaced):
        state.order_id = event.order_id
        state.customer_id = event.customer_id
        state.total = event.total
        state.status = "pending"
    elif isinstance(event, EvOrderShipped):
        state.tracking_number = event.tracking_number
        state.status = "shipped"
    
    return state
```

**Key Points:**
- `_evolve` is a **pure function** (no side effects)
- Always returns a new state
- Handle only your domain event types (system events are handled by the framework)
- Initialize state with `subscriptions=[]` if None

#### `event_to_cmd(event) -> Command | None`
Converts external events to commands, enabling event-driven workflows.

```python
@classmethod
def event_to_cmd(cls, e: ConsumedEvent) -> CmdShipOrder | None:
    # Convert external event to command
    if isinstance(e.event, EvWarehousePickupComplete):
        return CmdShipOrder(
            order_id=e.event.order_id,
            tracking_number=e.event.tracking_number
        )
    return None
```

**Key Points:**
- Enables workflows to react to external events
- Returns `None` if event should not trigger a command
- Used for workflow orchestration

#### `is_final_event(event) -> bool`
Indicates when a workflow has reached a terminal state.

```python
@staticmethod
def is_final_event(e: EvOrderPlaced | EvOrderShipped) -> bool:
    return isinstance(e, EvOrderDelivered)
```

**Example:**

```python
from fleuve.model import Adapter, ActionContext
from fleuve.stream import ConsumedEvent

class OrderAdapter(Adapter[EvOrderPlaced | EvOrderShipped, CmdPlaceOrder]):
    def __init__(self, email_service):
        self.email_service = email_service
    
    async def act_on(
        self, 
        event: ConsumedEvent[EvOrderPlaced | EvOrderShipped],
        context: ActionContext | None = None
    ):
        # Handle side effects based on event type
        if isinstance(event.event, EvOrderPlaced):
            # Send confirmation email
            await self.email_service.send_confirmation(
                customer_id=event.event.customer_id,
                order_id=event.event.order_id
            )
        elif isinstance(event.event, EvOrderShipped):
            # Send shipping notification
            await self.email_service.send_shipping_notification(
                customer_id=event.event.customer_id,
                tracking_number=event.event.tracking_number
            )
        
        # Optionally yield commands to process after action
        # yield SomeCommand(...)
        if False:
            yield
    
    def to_be_act_on(self, event: EvOrderPlaced | EvOrderShipped) -> bool:
        # Determine which events should trigger actions
        return isinstance(event, (EvOrderPlaced, EvOrderShipped))
```

**Best Practices:**
- Keep activities idempotent (safe to retry)
- Use checkpoints for long-running operations
- Handle failures gracefully
- Yield commands to trigger follow-up workflows if needed

**Using Checkpoints:**

Yield **CheckpointYield** from `act_on` to update and optionally persist checkpoint:

- `yield CheckpointYield(data=..., save_now=False)` — merge into checkpoint; persisted at end of action.
- `yield CheckpointYield(data=..., save_now=True)` — merge and persist immediately.

```python
from fleuve import CheckpointYield

async def act_on(self, event: ConsumedEvent, context: ActionContext | None = None):
    if context is None:
        if False:
            yield
        return
    
    if "step1_complete" not in context.checkpoint:
        await self.step1()
        yield CheckpointYield(data={"step1_complete": True}, save_now=False)
    
    yield CheckpointYield(data={"step2_progress": 50}, save_now=False)
    yield CheckpointYield(data={"step2_saved": True}, save_now=True)  # persist immediately
    
    if "step2_complete" not in context.checkpoint:
        await self.step2()
        yield CheckpointYield(data={"step2_complete": True}, save_now=False)
    
    await self.step3()
```

**Using timeouts:**

Yield **ActionTimeout** from `act_on` to run the remainder of the action under a time limit (e.g. for calls to external APIs or long-running work). If the rest of the action does not complete within the given seconds, `TimeoutError` is raised and the activity is marked failed (retries apply per your retry policy).

- `yield ActionTimeout(seconds=30.0)` — the rest of the action must finish within 30 seconds.

```python
from fleuve import ActionTimeout

async def act_on(self, event: ConsumedEvent, context: ActionContext | None = None):
    # Optional: do quick work before the timeout
    yield SomeCommand(...)

    yield ActionTimeout(seconds=30.0)  # remainder must finish in 30s
    await self.call_slow_external_api()
    yield CheckpointYield(data={"api_done": True}, save_now=False)
```

You can yield multiple `ActionTimeout` values; each applies to the following portion of the generator until the next timeout or the end.

### 6. Repository

The **AsyncRepo** manages workflow state and event persistence.

**Example:**

```python
from fleuve.repo import AsyncRepo, EuphStorageNATS
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Setup database
engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
session_maker = async_sessionmaker(engine)

# Setup NATS
nc = await NATS().connect("nats://localhost:4222")
ephemeral_storage = EuphStorageNATS(nc, "order_states", OrderState)

# Create repository (optional sync_db for strongly consistent denormalized tables)
repo = AsyncRepo(
    session_maker=session_maker,
    es=ephemeral_storage,
    model=OrderWorkflow,
    db_event_model=OrderEvent,
    db_sub_model=OrderSubscription,
    # sync_db=optional_handler,  # async (s, workflow_id, old_state, new_state, events) -> None
)

# Create new workflow
result = await repo.create_new(
    cmd=CmdPlaceOrder(order_id="123", customer_id="c1", total=100.0),
    workflow_id="order-123"
)

# Process command on existing workflow
result = await repo.process_command(
    workflow_id="order-123",
    cmd=CmdShipOrder(order_id="123", tracking_number="TRK123")
)

# Get current state
state = await repo.get_current_state(session, "order-123")
```

## Usage Examples

### Basic Workflow

Create a simple workflow that processes orders:

```python
from fleuve import Workflow, EventBase, StateBase
from fleuve.setup import create_workflow_runner

# Define your workflow (see Quick Start for full example)
class OrderWorkflow(Workflow[...]):
    ...

# Run it
async with create_workflow_runner(
    workflow_type=OrderWorkflow,
    state_type=OrderState,
) as resources:
    # Create workflow instance
    await resources.repo.create_new(cmd=CmdPlaceOrder(...), workflow_id="order-1")
    
    # Process commands
    await resources.repo.process_command("order-1", cmd=CmdShipOrder(...))
    
    # Run workflow runner
    await resources.runner.run()
```

### Workflow with Activities

Add side effects to your workflow:

```python
from fleuve.model import Adapter, ActionContext
from fleuve.stream import ConsumedEvent

class EmailAdapter(Adapter[OrderEvent, OrderCommand]):
    async def act_on(self, event: ConsumedEvent[OrderEvent], context: ActionContext | None = None):
        if isinstance(event.event, EvOrderPlaced):
            await send_confirmation_email(event.event.customer_id)
        if False:
            yield  # async generator; yield commands if any
    
    def to_be_act_on(self, event: OrderEvent) -> bool:
        return isinstance(event, EvOrderPlaced)

# Use adapter in setup
async with create_workflow_runner(
    workflow_type=OrderWorkflow,
    state_type=OrderState,
    adapter=EmailAdapter(),
) as resources:
    ...
```

### Cross-Workflow Communication

Workflows subscribe to events from other workflows by emitting sync events from `decide()`:

```python
from fleuve.model import Sub, EvSubscriptionAdded

# In OrderWorkflow.decide() - emit EvSubscriptionAdded to add a subscription
@staticmethod
def decide(state: OrderState | None, cmd: CmdPlaceOrder) -> list[OrderEvent] | Rejection:
    events = [EvOrderPlaced(...)]
    events.append(EvSubscriptionAdded(sub=Sub(
        event_type="payment.completed",
        workflow_id=f"payment-{cmd.order_id}"
    )))
    return events

# In OrderWorkflow.event_to_cmd()
@classmethod
def event_to_cmd(cls, e: ConsumedEvent) -> OrderCommand | None:
    if e.event.type == "payment.completed":
        return CmdReceivePayment(order_id=e.workflow_id, payment_id=e.event.payment_id)
    return None
```

See the [complete examples](./examples/) directory for more.

## Step-by-Step Tutorial

Let's build a complete order processing system from scratch.

### Step 1: Define Your Domain Models

Create a file `models.py`:

```python
from typing import Literal
from pydantic import BaseModel, Field
from fleuve.model import EventBase, StateBase

# Events
class EvOrderPlaced(EventBase):
    type: Literal["order.placed"] = "order.placed"
    order_id: str
    customer_id: str
    items: list[str]
    total: float

class EvPaymentReceived(EventBase):
    type: Literal["payment.received"] = "payment.received"
    order_id: str
    payment_id: str

class EvOrderShipped(EventBase):
    type: Literal["order.shipped"] = "order.shipped"
    order_id: str
    tracking_number: str

# Union type for all events
OrderEvent = EvOrderPlaced | EvPaymentReceived | EvOrderShipped

# Commands
class CmdPlaceOrder(BaseModel):
    order_id: str
    customer_id: str
    items: list[str] = Field(min_length=1)
    total: float = Field(gt=0)

class CmdReceivePayment(BaseModel):
    order_id: str
    payment_id: str

class CmdShipOrder(BaseModel):
    order_id: str
    tracking_number: str

OrderCommand = CmdPlaceOrder | CmdReceivePayment | CmdShipOrder

# State
class OrderState(StateBase):
    order_id: str | None = None
    customer_id: str | None = None
    items: list[str] = []
    total: float = 0.0
    payment_id: str | None = None
    tracking_number: str | None = None
    status: str = "new"  # new, paid, shipped
    subscriptions: list = []
```

### Step 2: Implement the Workflow

Create `workflow.py`:

```python
from fleuve.model import Workflow, Rejection
from fleuve.stream import ConsumedEvent
from models import (
    OrderEvent, OrderCommand, OrderState,
    EvOrderPlaced, EvPaymentReceived, EvOrderShipped,
    CmdPlaceOrder, CmdReceivePayment, CmdShipOrder,
)

class OrderWorkflow(Workflow[OrderEvent, OrderCommand, OrderState, ConsumedEvent]):
    @classmethod
    def name(cls) -> str:
        return "order"
    
    @staticmethod
    def decide(state: OrderState | None, cmd: OrderCommand) -> list[OrderEvent] | Rejection:
        # Handle CmdPlaceOrder
        if isinstance(cmd, CmdPlaceOrder):
            if state is not None:
                return Rejection(msg="Order already exists")
            return [EvOrderPlaced(
                order_id=cmd.order_id,
                customer_id=cmd.customer_id,
                items=cmd.items,
                total=cmd.total
            )]
        
        # Ensure order exists for other commands
        if state is None:
            return Rejection(msg="Order does not exist")
        
        # Handle CmdReceivePayment
        if isinstance(cmd, CmdReceivePayment):
            if state.status != "new":
                return Rejection(msg="Payment already received")
            return [EvPaymentReceived(
                order_id=cmd.order_id,
                payment_id=cmd.payment_id
            )]
        
        # Handle CmdShipOrder
        if isinstance(cmd, CmdShipOrder):
            if state.status != "paid":
                return Rejection(msg="Cannot ship unpaid order")
            return [EvOrderShipped(
                order_id=cmd.order_id,
                tracking_number=cmd.tracking_number
            )]
        
        return Rejection(msg="Unknown command")
    
    @staticmethod
    def _evolve(state: OrderState | None, event: OrderEvent) -> OrderState:
        if state is None:
            state = OrderState(subscriptions=[])
        
        if isinstance(event, EvOrderPlaced):
            state.order_id = event.order_id
            state.customer_id = event.customer_id
            state.items = event.items
            state.total = event.total
            state.status = "new"
        
        elif isinstance(event, EvPaymentReceived):
            state.payment_id = event.payment_id
            state.status = "paid"
        
        elif isinstance(event, EvOrderShipped):
            state.tracking_number = event.tracking_number
            state.status = "shipped"
        
        return state
    
    @classmethod
    def event_to_cmd(cls, e: ConsumedEvent) -> OrderCommand | None:
        # No external event handling in this example
        return None
    
    @staticmethod
    def is_final_event(e: OrderEvent) -> bool:
        return isinstance(e, EvOrderShipped)
```

### Step 3: Define Database Models

Create `db_models.py`:

```python
from sqlalchemy.orm import DeclarativeBase, mapped_column
from fleuve.postgres import (
    StoredEvent, Subscription, Activity, 
    DelaySchedule, Offset, PydanticType
)
from models import OrderEvent, OrderCommand

class Base(DeclarativeBase):
    pass

class OrderEventModel(StoredEvent, Base):
    __tablename__ = "order_events"
    body = mapped_column(PydanticType(OrderEvent))

class OrderSubscriptionModel(Subscription, Base):
    __tablename__ = "order_subscriptions"

class OrderActivityModel(Activity, Base):
    __tablename__ = "order_activities"

class OrderDelayScheduleModel(DelaySchedule, Base):
    __tablename__ = "order_delay_schedules"
    next_command = mapped_column(PydanticType(OrderCommand))

class OrderOffsetModel(Offset, Base):
    __tablename__ = "order_offsets"
```

### Step 4: Create an Adapter (Optional)

Create `adapter.py`:

```python
from fleuve.model import Adapter, ActionContext
from fleuve.stream import ConsumedEvent
from models import OrderEvent, OrderCommand, EvOrderPlaced, EvPaymentReceived

class OrderAdapter(Adapter[OrderEvent, OrderCommand]):
    def __init__(self, notification_service):
        self.notification_service = notification_service
    
    async def act_on(
        self, 
        event: ConsumedEvent[OrderEvent],
        context: ActionContext | None = None
    ):
        # Send notifications based on events
        if isinstance(event.event, EvOrderPlaced):
            await self.notification_service.send_order_confirmation(
                customer_id=event.event.customer_id,
                order_id=event.event.order_id,
                total=event.event.total
            )
        
        elif isinstance(event.event, EvPaymentReceived):
            await self.notification_service.send_payment_confirmation(
                customer_id=event.event.customer_id,
                payment_id=event.event.payment_id
            )
        
        # yield commands if any
        if False:
            yield
    
    def to_be_act_on(self, event: OrderEvent) -> bool:
        return isinstance(event, (EvOrderPlaced, EvPaymentReceived))
```

### Step 5: Set Up and Run

Create `main.py`:

```python
import asyncio
from nats.aio.client import Client as NATS
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fleuve.repo import AsyncRepo, EuphStorageNATS
from fleuve.config import WorkflowConfig, make_runner_from_config
from db_models import (
    Base, OrderEventModel, OrderSubscriptionModel,
    OrderActivityModel, OrderDelayScheduleModel, OrderOffsetModel
)
from models import OrderState
from workflow import OrderWorkflow
from adapter import OrderAdapter

class MockNotificationService:
    async def send_order_confirmation(self, customer_id: str, order_id: str, total: float):
        print(f"📧 Sent order confirmation to {customer_id} for order {order_id}")
    
    async def send_payment_confirmation(self, customer_id: str, payment_id: str):
        print(f"📧 Sent payment confirmation to {customer_id}")

async def main():
    # Database setup
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost/fleuve"
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # NATS setup
    nc = NATS()
    await nc.connect("nats://localhost:4222")
    
    # Ephemeral storage
    ephemeral_storage = EuphStorageNATS(nc, "order_states", OrderState)
    
    # Repository
    repo = AsyncRepo(
        session_maker=session_maker,
        es=ephemeral_storage,
        model=OrderWorkflow,
        db_event_model=OrderEventModel,
        db_sub_model=OrderSubscriptionModel,
    )
    
    # Configuration
    config = WorkflowConfig(
        nats_bucket="order_states",
        workflow_type=OrderWorkflow,
        adapter=OrderAdapter(MockNotificationService()),
        db_sub_type=OrderSubscriptionModel,
        db_event_model=OrderEventModel,
        db_activity_model=OrderActivityModel,
        db_delay_schedule_model=OrderDelayScheduleModel,
        db_offset_model=OrderOffsetModel,
    )
    
    # Create runner
    runner = make_runner_from_config(
        config=config,
        repo=repo,
        session_maker=session_maker,
    )
    
    # Run workflow system
    async with ephemeral_storage, runner:
        # Example: Create an order
        from models import CmdPlaceOrder, CmdReceivePayment
        
        order_id = "order-001"
        
        # Place order
        result = await repo.create_new(
            cmd=CmdPlaceOrder(
                order_id=order_id,
                customer_id="customer-123",
                items=["item1", "item2"],
                total=99.99
            ),
            workflow_id=order_id
        )
        print(f"✅ Order placed: {result}")
        
        # Receive payment
        await asyncio.sleep(1)  # Give time for events to process
        result = await repo.process_command(
            workflow_id=order_id,
            cmd=CmdReceivePayment(
                order_id=order_id,
                payment_id="pay-123"
            )
        )
        print(f"✅ Payment received: {result}")
        
        # Keep runner running to process events
        print("\n🏃 Runner is processing events... Press Ctrl+C to stop")
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 6: Run It!

```bash
# Make sure PostgreSQL and NATS are running
python main.py
```

You should see:

```
✅ Order placed: StoredState(id='order-001', state=OrderState(...), version=1)
📧 Sent order confirmation to customer-123 for order order-001
✅ Payment received: StoredState(id='order-001', state=OrderState(...), version=2)
📧 Sent payment confirmation to customer-123
🏃 Runner is processing events... Press Ctrl+C to stop
```

## Architecture

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Application                            │
│  ┌────────────┐         ┌────────────┐         ┌──────────┐ │
│  │  Commands  │────────▶│  Workflow  │────────▶│  Events  │ │
│  └────────────┘         │   .decide  │         └─────┬────┘ │
│                         └────────────┘               │      │
└──────────────────────────────────────────────────────┼──────┘
                                                       │
                    ┌──────────────────────────────────┼──────────────────┐
                    │                                  │                  │
                    ▼                                  ▼                  ▼
         ┌─────────────────────┐          ┌──────────────────┐   ┌─────────────┐
         │   PostgreSQL        │          │  Workflow.evolve │   │  Adapters   │
         │   (Event Store)     │          │                  │   │ (Side Effects)│
         │  - Events           │          │                  │   └─────────────┘
         │  - Activities       │          │                  │
         │  - Subscriptions    │          │                  │
         │  - Offsets          │          │                  │
         └─────────────────────┘          └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │   NATS KV        │
                                          │ (State Cache)    │
                                          │  - Fast reads    │
                                          │  - Ephemeral     │
                                          └──────────────────┘
```

### Component Responsibilities

#### **WorkflowsRunner**
- Reads events from PostgreSQL
- Processes commands through workflows
- Manages event stream reading with offset tracking
- Triggers side effects via adapters
- Handles scaling operations

#### **AsyncRepo**
- Persists events to PostgreSQL
- Manages state in NATS cache
- Processes commands through workflows
- Handles workflow creation and updates
- Optional `sync_db` or `adapter.sync_db`: runs custom DB updates in the same transaction as event insert (for strongly consistent denormalized/auxiliary data); when using `create_workflow_runner(adapter=...)`, the repo uses `adapter.sync_db` unless `sync_db` is passed explicitly

#### **ActionExecutor**
- Executes adapter actions
- Manages retry logic
- Handles checkpoint/resume
- Ensures idempotency
- Recovers interrupted actions

#### **DelayScheduler**
- Monitors delay schedules
- Emits resume events when delays complete
- Manages time-based workflow resumption

### Data Flow

1. **Command Processing**:
   ```
   Command → Workflow.decide → Events → PostgreSQL
   ```

2. **State Derivation**:
   ```
   Events → Workflow.evolve → State → NATS Cache
   ```

3. **Side Effect Execution**:
   ```
   Events → ActionExecutor → Adapter.act_on → External Systems
   ```

4. **Event Stream Processing**:
   ```
   PostgreSQL → Reader → WorkflowsRunner → event_to_cmd → Commands
   ```

## Advanced Features

### Command Gateway

The **FleuveCommandGateway** exposes workflow commands via HTTP for non-Python clients (e.g., frontends, mobile apps, other services). Mount it in your FastAPI app or use it via the Fleuve UI backend.

**Endpoints:**
- `POST /commands/{workflow_type}` — Create a new workflow (body: `workflow_id`, `command_type`, `payload`)
- `POST /commands/{workflow_type}/{workflow_id}` — Process a command on an existing workflow
- `POST /commands/{workflow_type}/{workflow_id}/pause` — Pause a workflow
- `POST /commands/{workflow_type}/{workflow_id}/resume` — Resume a paused workflow
- `POST /commands/{workflow_type}/{workflow_id}/cancel` — Cancel a workflow
- `POST /commands/retry/{workflow_id}/{activity_id}` — Retry a failed action (requires `action_executor`)

**Command parsers** map `(command_type, payload)` to your typed Command model:

```python
from fleuve.gateway import FleuveCommandGateway

def parse_order_command(cmd_type: str, payload: dict):
    if cmd_type == "place":
        return CmdPlaceOrder(**payload)
    if cmd_type == "ship":
        return CmdShipOrder(**payload)
    raise ValueError(f"Unknown command: {cmd_type}")

gateway = FleuveCommandGateway(
    repos={"order": repo},
    command_parsers={"order": parse_order_command},
    action_executor=executor,  # optional, for retry endpoint
)
app.include_router(gateway.router)
```

When using **Fleuve UI**, pass `repos` and `command_parsers` to `create_app`; the gateway is mounted automatically at `/commands`.

### Fleuve UI

The Fleuve UI is a web dashboard for monitoring workflows, events, activities, delays, and more. Run it via the CLI:

```bash
# Build frontend (once)
python scripts/build_ui.py

# Start the UI server (default: http://0.0.0.0:8001)
fleuve ui
```

Set `DATABASE_URL` and `NATS_URL` to point to your Fleuve database and NATS. The standalone UI uses default models and connects to any Fleuve database. For project-specific models, use the UI addon in your project (see `fleuve add ui`).

### Snapshots & Event Truncation

Reduce event replay time and storage by enabling **automatic snapshots** and **event truncation**.

**Snapshots** are periodic state checkpoints (e.g., every 3 events). When loading state, the repo uses the latest snapshot and replays only events after it.

**Truncation** deletes old events that are safely covered by snapshots. Events are only deleted when:
- A snapshot exists at version V (events before V are redundant)
- All readers have processed the event (global_id below min reader offset)
- The event has been published (pushed)
- The event is older than the configured min retention period

```python
# In create_workflow_runner or WorkflowConfig
db_snapshot_model=OrderSnapshotModel,
snapshot_interval=3,           # snapshot every 3 events
enable_truncation=True,
truncation_min_retention=timedelta(days=7),
truncation_batch_size=1000,
truncation_check_interval=timedelta(hours=1),
```

### Lifecycle Management

Workflows can be **paused**, **resumed**, or **cancelled** via system events. The `StateBase.lifecycle` field tracks `active`, `paused`, or `cancelled`.

```python
# Via AsyncRepo
await repo.pause_workflow("order-123")
await repo.resume_workflow("order-123")
await repo.cancel_workflow("order-123", reason="Customer requested cancellation")

# Via Command Gateway
POST /commands/order/order-123/pause
POST /commands/order/order-123/resume
POST /commands/order/order-123/cancel  # body: {"reason": "..."}
```

When a workflow is paused or cancelled, `process_command` rejects new commands with an appropriate message.

### Dead Letter Queue & Retry Failed Actions

When an activity exceeds its retry limit, it is marked as failed. You can:

1. **Retry via ActionExecutor**: `await action_executor.retry_failed_action(workflow_id, activity_id)`
2. **Retry via Command Gateway**: `POST /commands/retry/{workflow_id}/{activity_id}` (requires `action_executor` passed to the gateway)
3. **Optional callback**: Pass `on_action_failed` to the ActionExecutor for custom handling (alerts, external DLQ routing)

### OpenTelemetry Tracing

Enable optional tracing for observability:

```python
from fleuve.tracing import FleuveTracer

tracer = FleuveTracer(service_name="order-workflow")
# Pass to create_workflow_runner or WorkflowConfig
enable_otel=True
# Or set tracer explicitly in WorkflowConfig
```

Spans are created for `process_command`, `load_state`, `execute_action`, and Reader operations. Install `opentelemetry-api` and `opentelemetry-sdk` for full support; without them, a no-op tracer is used.

### Event Replay & Simulate

**Replay** reconstructs workflow state from events at a given version (time travel). The Fleuve UI exposes `GET /api/workflows/{id}/state/{version}` for this.

**Simulate** applies hypothetical commands without persisting. Useful for validation or what-if analysis:

```python
# Via Fleuve UI API when workflow_types and command_parsers are provided
POST /api/workflows/{workflow_id}/simulate
# body: {"command_type": "...", "payload": {...}}
# Returns the resulting state without persisting events
```

### Delays and Scheduling

Workflows can delay for a specified duration using `EvDelay` events. Both one-shot and recurring (cron) delays are supported.

#### One-shot delays

```python
from fleuve.model import EvDelay, EvDelayComplete, EventBase
from typing import Literal
import datetime

# Define a delay complete event
class EvReminderDelayComplete(EvDelayComplete):
    type: Literal["reminder.delay_complete"] = "reminder.delay_complete"
    at: datetime.datetime

# In your workflow decide method
@staticmethod
def decide(state: State | None, cmd: Command) -> list[Event] | Rejection:
    if isinstance(cmd, CmdScheduleReminder):
        # Schedule a one-shot delay
        delay_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        return [EvDelay(
            id="reminder-1",
            delay_until=delay_until,
            next_cmd=CmdSendReminder(user_id=cmd.user_id)
        )]
    
    if isinstance(cmd, CmdSendReminder):
        return [EvReminderSent(user_id=cmd.user_id)]
    
    return Rejection()
```

#### Recurring delays (cron)

Use `cron_expression` and `timezone` for recurring schedules. The DelayScheduler automatically re-inserts the next occurrence after each fire:

```python
# Daily at 9am UTC
EvDelay(
    id="daily-report",
    delay_until=datetime.datetime.now(datetime.timezone.utc),  # first fire computed from cron
    next_cmd=CmdGenerateReport(),
    cron_expression="0 9 * * *",   # croniter-compatible (min hour day month weekday)
    timezone="UTC"
)

# Every Monday at 8am in New York
EvDelay(
    id="weekly-sync",
    delay_until=...,
    next_cmd=CmdWeeklySync(),
    cron_expression="0 8 * * 1",
    timezone="America/New_York"
)
```

**How it works:**
1. Workflow emits `EvDelay` event with `delay_until`, `next_cmd`, and optionally `cron_expression` + `timezone`
2. `DelayScheduler` detects the event and stores the schedule
3. When time arrives, `DelayScheduler` emits `EvDelayComplete` event and processes `next_cmd`
4. For cron schedules, the scheduler computes the next fire time and re-inserts the schedule; for one-shot delays, the schedule is removed

### Workflow Versioning / Schema Evolution

When evolving event schemas, use `schema_version` and `upcast` to migrate old events:

**1. Add an optional field (no upcast needed):**
```python
class EvOrderPlaced(EventBase):
    type: Literal["order.placed"] = "order.placed"
    order_id: str
    amount: int
    notes: str = ""  # New optional field - old events load with default
```

**2. Rename a field (override `upcast`):**
```python
class MyWorkflow(Workflow[...]):
    @classmethod
    def schema_version(cls) -> int:
        return 2  # Bump when schema changes

    @classmethod
    def upcast(cls, event_type: str, schema_version: int, raw_data: dict) -> dict:
        if event_type == "order.placed" and schema_version < 2:
            raw_data["amount"] = raw_data.pop("total", 0)  # Rename total -> amount
        return raw_data
```

**3. Change a field type (override `upcast`):**
```python
@classmethod
def upcast(cls, event_type: str, schema_version: int, raw_data: dict) -> dict:
    if event_type == "order.placed" and schema_version < 2:
        raw_data["amount"] = int(raw_data.get("amount", 0))  # str -> int
    return raw_data
```

Add a `body_raw` generated column to your event model for upcasting:
```python
body_raw: Mapped[dict] = mapped_column(JSONB, Computed("body", persisted=True), nullable=True)
```

### Subscriptions (Cross-Workflow Communication)

Workflows subscribe to events by emitting `EvSubscriptionAdded` and `EvSubscriptionRemoved` from `decide()`. The system updates state and DB.

```python
from fleuve.model import Sub, EvSubscriptionAdded, EvSubscriptionRemoved

# In decide() - emit sync events to add/remove subscriptions
@staticmethod
def decide(state: OrderState | None, cmd: CmdPlaceOrder) -> list[Event] | Rejection:
    events = [EvOrderPlaced(...)]
    events.append(EvSubscriptionAdded(sub=Sub(
        event_type="payment.completed",
        workflow_id=f"payment-{cmd.order_id}"
    )))
    return events

# To remove: EvSubscriptionRemoved(sub=Sub(...))

# In event_to_cmd - react to subscribed events
@classmethod
def event_to_cmd(cls, e: ConsumedEvent) -> Command | None:
    if e.event.type == "payment.completed":
        return CmdReceivePayment(
            order_id=e.workflow_id,
            payment_id=e.event.payment_id
        )
    return None
```

**Subscription Patterns:**

```python
# Add subscription (emit from decide)
EvSubscriptionAdded(sub=Sub(event_type="payment.completed", workflow_id="payment-123"))
EvSubscriptionAdded(sub=Sub(event_type="*", workflow_id="payment-123"))  # all events from workflow
EvSubscriptionAdded(sub=Sub(event_type="payment.completed", workflow_id="*"))  # event type from any workflow

# Remove subscription
EvSubscriptionRemoved(sub=Sub(event_type="payment.completed", workflow_id="payment-123"))
```

**External subscriptions** (NATS topics): use `EvExternalSubscriptionAdded(sub=ExternalSub(topic="..."))` and `EvExternalSubscriptionRemoved(topic="...")`.

### Strongly consistent DB sync

Keep denormalized or auxiliary database tables in sync with the event stream by running updates in the **same transaction** as event insertion. When events are appended (via `create_new` or `process_command`), your handler runs inside that transaction—after subscription handling and before event insert—and can perform arbitrary DB writes that commit atomically with the events.

**Handler signature:** `async (session, workflow_id, old_state, new_state, events) -> None`

- `old_state` is `None` for `create_new`; otherwise the state before the new events.
- `new_state` is the evolved state after applying `events`.
- Do not commit inside the handler; the repo commits the transaction after event insert.

**Option 1: implement on the Adapter** (recommended when you already have an adapter)

```python
from fleuve.model import Adapter
from sqlalchemy import insert

class OrderAdapter(Adapter[OrderEvent, OrderCommand]):
    async def act_on(self, event, context=None):
        # ... side effects
        # yield commands if any
        if False:
            yield

    def to_be_act_on(self, event):
        return isinstance(event, EvOrderPlaced)

    async def sync_db(self, session, workflow_id, old_state, new_state, events):
        await session.execute(
            insert(OrderSummaryModel).values(
                workflow_id=workflow_id,
                total=new_state.total,
                status=new_state.status,
            )
        )

# create_workflow_runner passes adapter to the repo; repo uses adapter.sync_db
async with create_workflow_runner(
    workflow_type=OrderWorkflow,
    state_type=OrderState,
    adapter=OrderAdapter(),
) as resources:
    ...
```

**Option 2: pass a standalone sync_db callable**

```python
async def sync_order_summary(s, workflow_id, old_state, new_state, events):
    await s.execute(insert(OrderSummaryModel).values(...))

async with create_workflow_runner(
    workflow_type=OrderWorkflow,
    state_type=OrderState,
    sync_db=sync_order_summary,  # overrides adapter.sync_db when both present
) as resources:
    ...
```

**AsyncRepo:** Pass `adapter=...` and the repo uses `adapter.sync_db` when no explicit `sync_db` is given. Pass `sync_db=...` to override or when you have no adapter.

**Execution order:** lock/load state → decide → evolve → handle subscriptions → **sync_db** → inject tags → insert events → commit.

### Direct Messages

Send events directly to specific workflows:

```python
from fleuve.model import EvDirectMessage
from typing import Literal

class EvNotification(EvDirectMessage):
    type: Literal["notification"] = "notification"
    target_workflow_id: str
    target_workflow_type: str
    message: str

# In decide method
@staticmethod
def decide(state: State | None, cmd: CmdNotifyUser) -> list[Event] | Rejection:
    return [EvNotification(
        target_workflow_id=f"user-{cmd.user_id}",
        target_workflow_type="user",
        message=cmd.message
    )]
```

### Retry Policies

Configure retry behavior for actions:

```python
from fleuve.postgres import RetryPolicy
import datetime

# Custom retry policy
retry_policy = RetryPolicy(
    max_retries=5,
    backoff_strategy="exponential",  # or "linear"
    backoff_factor=2.0,
    backoff_min=datetime.timedelta(seconds=1),
    backoff_max=datetime.timedelta(minutes=5),
    backoff_jitter=0.1,  # Add 10% randomness
)

# You can modify retry policy in ActionContext
async def act_on(self, event: ConsumedEvent, context: ActionContext | None):
    if context:
        # Increase retries for this specific action
        context.retry_policy.max_retries = 10
    
    # ... perform action; yield commands if any
    if False:
        yield
```

### Event Encryption

Encrypt sensitive event data:

```python
import os
from fleuve.postgres import EncryptedPydanticType

# Set encryption key
os.environ["STORAGE_KEY"] = "your-32-character-encryption-key"

# Use encrypted column in your event model
class SensitiveEventModel(StoredEvent, Base):
    __tablename__ = "sensitive_events"
    body = mapped_column(EncryptedPydanticType(SensitiveEvent))
```

## Horizontal Scaling

Fleuve supports horizontal scaling through hash-based partitioning.

### Basic Partitioning

Run multiple instances of your workflow runner, each handling a partition of workflow IDs:

```python
from fleuve.config import make_partitioned_runner_from_config
from fleuve.partitioning import PartitionedRunnerConfig
import os

# Configuration from environment
PARTITION_INDEX = int(os.getenv("PARTITION_INDEX", "0"))
TOTAL_PARTITIONS = int(os.getenv("TOTAL_PARTITIONS", "3"))

# Create partition configuration
partition_config = PartitionedRunnerConfig(
    partition_index=PARTITION_INDEX,
    total_partitions=TOTAL_PARTITIONS,
    workflow_type=OrderWorkflow.name(),
)

# Create partitioned runner
runner = make_partitioned_runner_from_config(
    config=workflow_config,
    partition_config=partition_config,
    repo=repo,
    session_maker=session_maker,
)

# Run
async with runner:
    await runner.run()
```

### Running Partitioned Instances

```bash
# Terminal 1 - Partition 0
export PARTITION_INDEX=0
export TOTAL_PARTITIONS=3
python main.py

# Terminal 2 - Partition 1
export PARTITION_INDEX=1
export TOTAL_PARTITIONS=3
python main.py

# Terminal 3 - Partition 2
export PARTITION_INDEX=2
export TOTAL_PARTITIONS=3
python main.py
```

### Scaling Operations

#### Scaling Up (Adding Partitions)

```python
from fleuve.scaling import rebalance_partitions
from fleuve.partitioning import create_partitioned_configs

# Current configuration (3 partitions)
old_configs = create_partitioned_configs(3, "order")

# New configuration (5 partitions)
new_configs = create_partitioned_configs(5, "order")

# Perform rebalancing
await rebalance_partitions(
    session_maker=session_maker,
    offset_model=OrderOffsetModel,
    old_partition_configs=old_configs,
    new_partition_configs=new_configs,
)
```

#### Scaling Down (Removing Partitions)

```python
# Current configuration (5 partitions)
old_configs = create_partitioned_configs(5, "order")

# New configuration (3 partitions)
new_configs = create_partitioned_configs(3, "order")

# Perform rebalancing
await rebalance_partitions(
    session_maker=session_maker,
    offset_model=OrderOffsetModel,
    old_partition_configs=old_configs,
    new_partition_configs=new_configs,
)
```

### Zero-Downtime Scaling

1. **Start new partition instances** (with new partition count)
2. **Trigger scaling operation** (rebalance_partitions)
3. **Old instances gracefully stop** when they detect scaling operation
4. **New instances take over** their assigned partitions

See [PARTITIONING.md](./PARTITIONING.md) for detailed information.

## API Reference

### Core Classes

#### `Workflow[E, C, S, EE]`

Base class for workflow implementations.

**Type Parameters:**
- `E`: Event type (union of all event types)
- `C`: Command type (union of all command types)
- `S`: State type
- `EE`: External event type

**Abstract Methods:**
- `name() -> str`: Return unique workflow identifier
- `decide(state, cmd) -> list[E] | Rejection`: Process command and return events (emit `EvSubscriptionAdded`, `EvScheduleAdded`, etc. for sync)
- `_evolve(state, event) -> S`: Apply domain event to state (you implement; system events handled by framework)
- `event_to_cmd(event) -> C | None`: Convert external events to commands
- `is_final_event(event) -> bool`: Check if event is terminal

#### `AsyncRepo`

Repository for workflow state and event persistence.

**Optional constructor args:** `sync_db: SyncDbHandler | None` — explicit async callable for strongly consistent DB updates; `adapter: Adapter | None` — when provided and `sync_db` is not, the repo uses `adapter.sync_db`. Handler signature: `(session, workflow_id, old_state, new_state, events) -> None`; runs in the same transaction as event insert (after subscription handling, before event insert). Must not commit inside the handler.

**Methods:**
- `create_new(cmd, workflow_id) -> StoredState | Rejection`: Create new workflow
- `process_command(workflow_id, cmd) -> StoredState | Rejection`: Process command
- `get_current_state(session, workflow_id) -> StoredState`: Get current state
- `load_state(session, workflow_id, at_version?) -> StoredState`: Load state from events

#### `Adapter[E, C]`

Base class for side effect handlers.

**Abstract Methods:**
- `act_on(event, context?)`: Async generator yielding zero or more **commands** (each applied to the same workflow), **CheckpointYield** (checkpoint data; `save_now=True` = persist immediately, `save_now=False` = persist at end), and/or **ActionTimeout** (time limit in seconds for the remainder of the action; uses `asyncio.wait_for`; on timeout, `TimeoutError` is raised and the action fails)
- `to_be_act_on(event) -> bool`: Determine if event should trigger action

#### `ActionContext`

Context for action execution with checkpoint support.

**Fields:**
- `workflow_id: str`: Workflow identifier
- `event_number: int`: Event sequence number
- `checkpoint: dict`: Checkpoint data
- `retry_count: int`: Current retry attempt
- `retry_policy: RetryPolicy`: Retry configuration

**Checkpoint updates:** In `act_on` yield `CheckpointYield(data=..., save_now=False)` (persist at end) or `CheckpointYield(data=..., save_now=True)` (persist immediately).

#### `CheckpointYield`

Checkpoint data yielded from `act_on` to update and optionally persist checkpoint.

**Fields:**
- `data: dict`: Checkpoint data to merge into context.checkpoint
- `save_now: bool = False`: If True, persist immediately to the DB; if False, persist at end of action

#### `ActionTimeout`

Time limit for the remainder of the action, yielded from `act_on`. The executor runs the rest of the generator inside `asyncio.wait_for(..., timeout=seconds)`. If that portion does not complete in time, `TimeoutError` is raised and the activity is marked failed (retries apply).

**Fields:**
- `seconds: float`: Timeout in seconds (must be > 0) for the remainder of the action

### Configuration

#### `WorkflowConfig`

Configuration for workflow runner.

**Fields:**
- `nats_bucket: str`: NATS bucket name for state caching
- `workflow_type: Type[Workflow]`: Workflow class
- `adapter: Adapter`: Side effect handler
- `db_sub_type: Type[Subscription]`: Subscription model
- `db_event_model: Type[StoredEvent]`: Event model
- `db_activity_model: Type[Activity]`: Activity model
- `db_delay_schedule_model: Type[DelaySchedule]`: Delay schedule model
- `db_offset_model: Type[Offset]`: Offset model
- `sync_db: SyncDbHandler | None`: Optional handler for strongly consistent DB updates in same transaction as event insert (pass to `AsyncRepo` when building repo from config)

#### Helper Functions

```python
# Create standard runner
runner = make_runner_from_config(
    config: WorkflowConfig,
    repo: AsyncRepo,
    session_maker: async_sessionmaker,
) -> WorkflowsRunner

# Create partitioned runner
runner = make_partitioned_runner_from_config(
    config: WorkflowConfig,
    partition_config: PartitionedRunnerConfig,
    repo: AsyncRepo,
    session_maker: async_sessionmaker,
) -> WorkflowsRunner
```

## Examples

### Complete Examples

- **[Traffic Fine Workflow](./examples/traffic_fine/)**: Full implementation of the workflow pattern with state machine, side effects, and web UI

### Example Snippets

See the examples directory for more:

```bash
# Run traffic fine example
python -m examples.traffic_fine.example

# Run with web UI
cd examples/traffic_fine
./build_web.sh
./start_api.sh
```

## Best Practices

### Workflow Design

1. **Keep decide() pure**: No I/O, no side effects, only business logic
2. **Keep _evolve() pure**: Only derive state from domain events
3. **Use descriptive event names**: Past tense, specific (e.g., `EvOrderPlaced`)
4. **Include all data in events**: Events should be self-contained
5. **Validate in decide()**: Reject invalid commands before emitting events

### State Management

1. **Use default values**: All state fields should have defaults
2. **Keep state minimal**: Don't store computed values
3. **Always include subscriptions**: Required field for cross-workflow communication
4. **State is ephemeral**: Can always be reconstructed from events

### Side Effects

1. **Use adapters for I/O**: Keep workflows pure, side effects in adapters
2. **Implement idempotency**: Actions should be safe to retry
3. **Use checkpoints for long operations**: Save progress periodically
4. **Handle failures gracefully**: Implement proper error handling

### Performance

1. **Use NATS caching**: Faster state access than querying events
2. **Batch event processing**: Process events in batches when possible
3. **Monitor partition sizes**: Rebalance if partitions are uneven
4. **Use appropriate retry policies**: Balance between reliability and performance

### Testing

1. **Test decide() with unit tests**: Pure function, easy to test
2. **Test _evolve() with unit tests**: Pure function, easy to test
3. **Test workflows end-to-end**: Integration tests with real database
4. **Mock adapters for testing**: Test workflow logic separately from I/O

Example test:

```python
def test_order_workflow_decide():
    # Test creation
    cmd = CmdPlaceOrder(order_id="123", customer_id="c1", total=100.0)
    result = OrderWorkflow.decide(None, cmd)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], EvOrderPlaced)
    
    # Test rejection
    state = OrderState(order_id="123", subscriptions=[])
    result = OrderWorkflow.decide(state, cmd)
    assert isinstance(result, Rejection)

def test_order_workflow_evolve():
    event = EvOrderPlaced(order_id="123", customer_id="c1", total=100.0)
    state = OrderWorkflow._evolve(None, event)
    assert state.order_id == "123"
    assert state.customer_id == "c1"
    assert state.total == 100.0
    assert state.status == "new"
```

## Production Deployment

### Environment Configuration

```bash
# Database
export DATABASE_URL="postgresql+asyncpg://user:password@db-host:5432/fleuve"

# NATS
export NATS_URL="nats://nats-host:4222"

# Encryption (optional)
export STORAGE_KEY="your-32-character-encryption-key-here"

# Partitioning
export PARTITION_INDEX=0
export TOTAL_PARTITIONS=3
```

### Database Migrations

Use Alembic for schema management:

```bash
# Initialize alembic
alembic init migrations

# Create migration
alembic revision --autogenerate -m "Add order tables"

# Apply migrations
alembic upgrade head
```

### Monitoring and Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Fleuve components log to their respective loggers:
# - fleuve.runner
# - fleuve.actions
# - fleuve.delay
# - fleuve.stream
# - fleuve.repo
```

### Graceful Shutdown

```python
import signal
import asyncio

shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def main():
    async with runner:
        # Start runner
        run_task = asyncio.create_task(runner.run())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Graceful shutdown
        print("Shutting down gracefully...")
        runner.stop()
        await run_task
```

### Health Checks

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    # Check database connectivity
    async with session_maker() as session:
        await session.execute("SELECT 1")
    
    # Check NATS connectivity
    if not nc.is_connected:
        raise Exception("NATS not connected")
    
    return {"status": "healthy"}
```

### Docker Deployment

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

# Copy application
COPY . .

# Run
CMD ["poetry", "run", "python", "main.py"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-workflow
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-workflow
  template:
    metadata:
      labels:
        app: order-workflow
    spec:
      containers:
      - name: worker
        image: myregistry/order-workflow:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        - name: NATS_URL
          value: "nats://nats:4222"
        - name: PARTITION_INDEX
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: TOTAL_PARTITIONS
          value: "3"
```

## Troubleshooting

### Common Issues

#### "column does not exist" Error

**Problem**: Database schema doesn't match code.

**Solution**: Recreate tables or run migrations:

```python
# Recreate all tables (WARNING: deletes data)
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.drop_all)
    await conn.run_sync(Base.metadata.create_all)
```

#### Events Not Processing

**Problem**: Runner not reading events.

**Solutions**:
1. Check runner is started: `await runner.start()`
2. Check offset is not stuck: Query offset table
3. Check for errors in logs
4. Verify NATS connection

#### State Not Updating

**Problem**: Cached state is stale.

**Solutions**:
1. Clear NATS cache for workflow
2. Check ephemeral storage is connected
3. Verify _evolve() is implemented correctly

#### Actions Failing

**Problem**: Adapter actions throwing errors.

**Solutions**:
1. Check action logs for exceptions
2. Verify retry policy is configured
3. Check checkpoint data is being saved
4. Ensure external services are reachable

#### Scaling Issues

**Problem**: Partitions not balanced.

**Solutions**:
1. Verify partition configuration is correct
2. Run rebalance operation
3. Check all runners have same TOTAL_PARTITIONS
4. Verify workflow IDs are evenly distributed

### Debug Mode

Enable detailed logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('fleuve').setLevel(logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### Getting Help

- **Documentation**: This README and code comments
- **Examples**: See `examples/` directory
- **Issues**: Report bugs on GitHub
- **Community**: Join discussions on GitHub Discussions

## Resources

### Documentation
- **Full Documentation**: This README covers all core concepts and features
- **API Reference**: See [API Reference](#api-reference) section above
- **Partitioning Guide**: See [PARTITIONING.md](./PARTITIONING.md) for scaling details

### Examples
- **Traffic Fine Workflow**: Complete example with web UI - see [examples/traffic_fine/](./examples/traffic_fine/)
- **Quick Start**: Minimal example in [Quick Start](#quick-start) section
- **Step-by-Step Tutorial**: Complete tutorial in [Step-by-Step Tutorial](#step-by-step-tutorial) section

### Community
- **GitHub Repository**: [github.com/doomervibe/fleuve](https://github.com/doomervibe/fleuve)
- **Issue Tracker**: [Report bugs or request features](https://github.com/doomervibe/fleuve/issues)
- **Contributing**: See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines

### Related Projects
- **Temporal**: Similar workflow framework (different language/approach). See [Why Fleuve? (vs Temporal)](#why-fleuve-vs-temporal) for a comparison.
- **The Workflow Pattern**: [Blog post](https://blog.bittacklr.be/the-workflow-pattern.html) that inspired Fleuve

### Built With
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation and settings management
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database toolkit
- [NATS](https://nats.io/) - Messaging system for state caching

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

See [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed guidelines.

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Inspired by [The Workflow Pattern](https://blog.bittacklr.be/the-workflow-pattern.html)
- Built with [Pydantic](https://pydantic-docs.helpmanual.io/), [SQLAlchemy](https://www.sqlalchemy.org/), and [NATS](https://nats.io/)

---

**Fleuve** - Flow like a river, scale like a stream. 🌊
