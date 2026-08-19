# Task Viewer Tests

This directory contains the test suite for the Shrimp Task Viewer application.

## Quick Start

```bash
# Install dependencies
npm install

# Run all tests
npm test

# Run tests with coverage
npm run test:coverage

# Run tests in watch mode
npm test -- --watch

# Run tests with UI
npm run test:ui
```

## Test Files

- `server.test.js` - Tests for the HTTP server and API endpoints
- `integration.test.js` - Full stack integration tests
- `edge-cases.test.js` - Edge case and error handling tests
- `test-utils.js` - Shared test utilities and mock helpers

## Component Tests

Component tests are located in `src/test/`:
- `App.test.jsx` - Main application component
- `TaskTable.test.jsx` - Task table component
- `TaskDetailView.test.jsx` - Task detail view component

## Using the Test Runner

We provide a convenient test runner script:

```bash
# Run all tests
./run-tests.sh all

# Run specific test categories
./run-tests.sh unit
./run-tests.sh integration
./run-tests.sh server
./run-tests.sh component
./run-tests.sh edge

# Run with coverage
./run-tests.sh coverage

# Run in watch mode
./run-tests.sh watch

# Run specific file
./run-tests.sh specific test/server.test.js
```

## Writing Tests

### Basic Test Structure
```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

describe('Component Name', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should do something', async () => {
    // Arrange
    const mockData = { /* ... */ };
    
    // Act
    render(<Component data={mockData} />);
    
    // Assert
    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  });
});
```

### Using Test Utilities
```javascript
import { createMockTask, mockFetch, validate } from './test-utils';

it('displays tasks', async () => {
  const tasks = [
    createMockTask({ name: 'Task 1' }),
    createMockTask({ name: 'Task 2' })
  ];

  mockFetch({
    '/api/tasks': { json: { tasks } }
  });

  render(<TaskList />);

  await waitFor(() => {
    validate.taskInTable(screen, tasks[0]);
    validate.taskInTable(screen, tasks[1]);
  });
});
```

## Debugging Tests

1. **Print DOM state**
   ```javascript
   screen.debug();
   ```

2. **Run single test**
   ```javascript
   it.only('test to debug', () => {
     // This test runs alone
   });
   ```

3. **Use test UI**
   ```bash
   npm run test:ui
   ```

## Coverage Reports

After running tests with coverage, open the HTML report:
```bash
npm run test:coverage
open coverage/index.html
```

Coverage goals:
- Lines: 80%+
- Functions: 80%+
- Branches: 80%+
- Statements: 80%+

## Common Issues

### Tests Timing Out
- Increase timeout: `{ timeout: 5000 }`
- Check for missing `await` statements
- Verify mocks are returning data

### Elements Not Found
- Use `screen.debug()` to inspect DOM
- Check if element is conditionally rendered
- Use appropriate query method (getBy, findBy, queryBy)

### Async Issues
- Always use `waitFor` for async operations
- Mock timers when testing intervals: `vi.useFakeTimers()`
- Clean up timers: `vi.useRealTimers()`

## Contributing

When adding new features:
1. Write tests first (TDD approach)
2. Ensure all tests pass
3. Maintain coverage above 80%
4. Update test documentation if needed

See `TEST_GUIDE.md` for comprehensive testing documentation.