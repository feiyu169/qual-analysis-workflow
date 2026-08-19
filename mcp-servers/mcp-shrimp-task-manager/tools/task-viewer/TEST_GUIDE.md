# Shrimp Task Viewer - Test Suite Guide

## Overview

This document describes the comprehensive test suite for the Shrimp Task Viewer application. The test suite uses Vitest as the testing framework and includes unit tests, component tests, integration tests, and edge case coverage.

## Test Structure

```
tools/task-viewer/
├── test/                       # Node.js server tests
│   ├── server.test.js         # HTTP server endpoint tests
│   ├── integration.test.js    # Full stack integration tests
│   ├── edge-cases.test.js     # Edge case and error handling tests
│   └── test-utils.js          # Shared test utilities
├── src/test/                  # React component tests
│   ├── setup.js               # Test environment setup
│   ├── App.test.jsx           # Main App component tests
│   ├── TaskTable.test.jsx     # TaskTable component tests
│   └── TaskDetailView.test.jsx # TaskDetailView component tests
├── vitest.config.js           # Main test configuration
└── vitest.config.coverage.js  # Coverage configuration
```

## Running Tests

### Install Dependencies
```bash
npm install
```

### Run All Tests
```bash
npm test
```

### Run Tests in Watch Mode
```bash
npm test -- --watch
```

### Run Tests with UI
```bash
npm run test:ui
```

### Run Tests with Coverage
```bash
npm run test:coverage
# or
npm test -- --coverage
```

### Run Specific Test Files
```bash
# Run server tests only
npm test test/server.test.js

# Run component tests only
npm test src/test/

# Run tests matching pattern
npm test -- --grep "profile"
```

## Test Categories

### 1. Server Tests (`test/server.test.js`)

Tests for the Node.js HTTP server including:

- **Settings Management**
  - Loading settings from file
  - Creating default settings
  - Saving settings with proper format

- **API Endpoints**
  - `GET /api/agents` - List profiles
  - `POST /api/add-profile` - Add new profile (multipart & URL-encoded)
  - `DELETE /api/remove-profile/:id` - Remove profile
  - `GET /api/tasks/:agentId` - Get tasks for agent
  - CORS headers and preflight requests

- **Static File Serving**
  - Serving React app files
  - Correct MIME types
  - SPA route handling
  - Cache control headers

- **Error Handling**
  - Server startup errors
  - Malformed JSON
  - File read errors

### 2. Component Tests

#### App Component (`src/test/App.test.jsx`)
- Profile loading and display
- Task loading when profile selected
- Search/filter functionality
- Add/remove profile operations
- Auto-refresh feature
- Manual refresh
- Tab drag-and-drop reordering
- Error state handling

#### TaskTable Component (`src/test/TaskTable.test.jsx`)
- Table rendering with all columns
- Task data display
- Status badge styling
- Date formatting
- Notes display
- Sorting by columns
- Pagination controls
- Filtering/search
- Task selection (click to view details)
- Empty state handling
- Large dataset performance

#### TaskDetailView Component (`src/test/TaskDetailView.test.jsx`)
- Task details display
- All field sections (description, notes, etc.)
- Dependencies list
- Related files with icons
- Status colors
- Date formatting
- Back button navigation
- Null/missing field handling

### 3. Integration Tests (`test/integration.test.js`)

Full application flow tests:
- Complete user workflows
- Profile switching with task loading
- Search and filtering across profiles
- Add/remove profile integration
- Auto-refresh with real timers
- Error handling integration
- Performance with large datasets

### 4. Edge Cases (`test/edge-cases.test.js`)

- **Network Errors**
  - Timeouts
  - Intermittent failures
  - Malformed responses

- **Data Integrity**
  - Circular dependencies
  - Extremely long content
  - XSS prevention
  - Unicode/emoji handling

- **State Management**
  - Rapid profile switching
  - Special characters in search
  - Concurrent operations

- **Browser Compatibility**
  - Missing localStorage
  - File input restrictions

- **Performance**
  - Large datasets (10,000+ tasks)
  - Rapid filtering

- **Memory Leaks**
  - Cleanup on unmount
  - Async operation handling

## Test Utilities (`test/test-utils.js`)

### Mock Data Generators
```javascript
createMockTask(overrides)      // Generate single task
createMockProfile(overrides)   // Generate single profile
createMockTasks(count, overrides) // Generate multiple tasks
```

### Mock Helpers
```javascript
mockFetch(responses)           // Mock fetch with responses
mockFileSystem(files)          // Mock fs operations
```

### Query Helpers
```javascript
queries.getTaskRow(screen, taskName)
queries.getStatusBadge(screen, status)
queries.getPaginationInfo(screen)
```

### Event Helpers
```javascript
events.selectProfile(screen, profileName)
events.searchTasks(screen, searchTerm, user)
events.clickTask(screen, taskName)
```

### Validation Helpers
```javascript
validate.taskInTable(screen, task)
validate.taskNotInTable(screen, task)
validate.profilesLoaded(screen, profiles)
```

## Test Coverage Goals

- **Line Coverage**: 80%+
- **Function Coverage**: 80%+
- **Branch Coverage**: 80%+
- **Statement Coverage**: 80%+

Coverage reports are generated in the `coverage/` directory.

## Best Practices

1. **Test Organization**
   - Group related tests using `describe` blocks
   - Use descriptive test names
   - Follow AAA pattern (Arrange, Act, Assert)

2. **Mocking**
   - Mock external dependencies (fetch, fs)
   - Use test utilities for consistent mocks
   - Clear mocks between tests

3. **Async Testing**
   - Use `waitFor` for async operations
   - Test loading states
   - Test error states

4. **User Interactions**
   - Use `userEvent` for realistic interactions
   - Test keyboard navigation
   - Test rapid user actions

5. **Edge Cases**
   - Test with empty data
   - Test with malformed data
   - Test boundary conditions
   - Test error scenarios

## Common Test Patterns

### Testing Async Data Loading
```javascript
it('loads data on mount', async () => {
  mockFetch({
    '/api/endpoint': { json: mockData }
  });

  render(<Component />);

  await waitFor(() => {
    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  });
});
```

### Testing User Interactions
```javascript
it('handles user input', async () => {
  const user = userEvent.setup();
  render(<Component />);

  const input = screen.getByRole('textbox');
  await user.type(input, 'test input');

  expect(input.value).toBe('test input');
});
```

### Testing Error States
```javascript
it('displays error on failure', async () => {
  mockFetch({
    '/api/endpoint': { ok: false, status: 500 }
  });

  render(<Component />);

  await waitFor(() => {
    expect(screen.getByText(/Error/)).toBeInTheDocument();
  });
});
```

## Debugging Tests

### Run Single Test
```javascript
it.only('specific test', () => {
  // This test runs in isolation
});
```

### Skip Test
```javascript
it.skip('not ready yet', () => {
  // This test is skipped
});
```

### Debug Output
```javascript
screen.debug(); // Print DOM
console.log(screen.getByRole('button')); // Log element
```

### Interactive Mode
```bash
npm run test:ui
```

## CI/CD Integration

The test suite is designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run Tests
  run: npm test -- --run

- name: Generate Coverage
  run: npm run test:coverage

- name: Upload Coverage
  uses: codecov/codecov-action@v3
```

## Troubleshooting

### Common Issues

1. **Tests timing out**
   - Increase timeout: `{ timeout: 5000 }`
   - Check for missing `await`
   - Verify mocks are returning data

2. **Elements not found**
   - Use `screen.debug()` to inspect DOM
   - Check element is rendered
   - Use correct query method

3. **Async issues**
   - Always use `waitFor` for async operations
   - Mock timers when testing intervals
   - Clean up intervals/timeouts

4. **Mock conflicts**
   - Clear mocks in `beforeEach`
   - Check mock implementation
   - Verify mock call order

## Future Improvements

1. **E2E Tests**
   - Add Playwright/Cypress for E2E testing
   - Test real server interactions
   - Test file uploads

2. **Performance Tests**
   - Add performance benchmarks
   - Test render performance
   - Memory usage monitoring

3. **Accessibility Tests**
   - Add axe-core integration
   - Test screen reader compatibility
   - Keyboard navigation coverage

4. **Visual Regression**
   - Add snapshot testing
   - Visual diff testing
   - Component screenshot tests