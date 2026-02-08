# Mock Data for UI Development

This project includes a mock data system that allows you to develop and test the UI without needing a running backend.

## How to Enable Mock Data

### Option 1: Environment Variable (Recommended for Development)

Create a `.env` file in the `fleuve_ui/frontend/` directory:

```bash
VITE_USE_MOCK_DATA=true
```

Then restart your dev server.

### Option 2: Browser Console (Quick Toggle)

Open your browser's developer console and run:

```javascript
localStorage.setItem('USE_MOCK_DATA', 'true');
```

Then refresh the page. To disable:

```javascript
localStorage.removeItem('USE_MOCK_DATA');
```

### Option 3: Code (Permanent)

Edit `fleuve_ui/frontend/src/api.js` and change:

```javascript
const USE_MOCK_DATA = true; // Change to true
```

## Mock Data Features

The mock data system includes:

- **10 sample workflows** across 4 different workflow types:
  - `traffic_fine` - Traffic violation processing
  - `order_processing` - E-commerce order management
  - `payment_workflow` - Payment processing
  - `document_approval` - Document review and approval

- **Dashboard statistics** with realistic numbers for:
  - Total workflows, events, activities, and delays
  - Breakdowns by type and status
  - Chart data for visualizations

- **Workflow details** including:
  - State snapshots at different versions
  - Event history
  - Activity logs
  - Delay schedules
  - Subscriptions

- **Filtering and pagination** support:
  - All API endpoints respect filter parameters
  - Pagination works as expected
  - Search functionality is simulated

## Visual Indicator

When mock mode is enabled, you'll see a small "mock" badge next to the "les" logo in the navigation bar. This helps you remember you're using mock data.

## Customizing Mock Data

To customize the mock data, edit `fleuve_ui/frontend/src/mockData.js`. You can:

- Add more workflows
- Modify workflow states
- Change statistics
- Add new event types
- Customize activity statuses

## API Compatibility

The mock data system is designed to match the real API structure exactly. All endpoints return data in the same format as the backend, so switching between mock and real data should be seamless.

## Notes

- Mock data includes simulated delays (300ms) to mimic real API calls
- Data is generated fresh on each page load (some IDs may change)
- Filtering and pagination work client-side
- All dates are relative (e.g., "2 days ago", "5 hours ago")
