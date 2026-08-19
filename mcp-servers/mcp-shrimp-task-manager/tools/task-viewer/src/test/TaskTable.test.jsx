import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TaskTable from '../components/TaskTable';

describe('TaskTable Component', () => {
  const mockTasks = [
    {
      id: 'task1',
      name: 'Complete authentication system',
      description: 'Implement OAuth2 authentication with JWT tokens',
      status: 'completed',
      createdAt: '2025-01-01T10:00:00Z',
      updatedAt: '2025-01-02T15:30:00Z',
      notes: 'Remember to implement refresh token rotation',
      completedAt: '2025-01-02T15:30:00Z'
    },
    {
      id: 'task2',
      name: 'Setup database schema', 
      description: 'Create PostgreSQL tables and relationships with proper indexes for optimal performance',
      status: 'in_progress',
      createdAt: '2025-01-02T09:00:00Z',
      updatedAt: '2025-01-03T11:45:00Z',
      notes: 'Use UUID for primary keys'
    },
    {
      id: 'task3',
      name: 'Write unit tests',
      description: 'Add comprehensive test coverage for API endpoints',
      status: 'pending',
      createdAt: '2025-01-03T14:00:00Z',
      updatedAt: '2025-01-03T14:00:00Z',
      notes: null
    },
    {
      id: 'task4',
      name: 'Deploy to staging',
      description: 'Setup CI/CD pipeline and deploy to staging environment',
      status: 'blocked',
      createdAt: '2025-01-04T10:00:00Z',
      updatedAt: '2025-01-04T10:00:00Z',
      notes: 'Waiting for DevOps team approval'
    }
  ];

  const mockOnFilterChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders all table columns correctly', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Check headers
      expect(screen.getByText('#')).toBeInTheDocument();
      expect(screen.getByText('Task Name')).toBeInTheDocument();
      expect(screen.getByText('Description')).toBeInTheDocument();
      expect(screen.getByText('Status')).toBeInTheDocument();
      expect(screen.getByText('Created')).toBeInTheDocument();
      expect(screen.getByText('Updated')).toBeInTheDocument();
      expect(screen.getByText('Notes')).toBeInTheDocument();
    });

    it('renders task data correctly', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Check task names
      expect(screen.getByText('Complete authentication system')).toBeInTheDocument();
      expect(screen.getByText('Setup database schema')).toBeInTheDocument();
      expect(screen.getByText('Write unit tests')).toBeInTheDocument();
      expect(screen.getByText('Deploy to staging')).toBeInTheDocument();

      // Check task numbers
      expect(screen.getByText('TASK 1')).toBeInTheDocument();
      expect(screen.getByText('TASK 2')).toBeInTheDocument();
      expect(screen.getByText('TASK 3')).toBeInTheDocument();
      expect(screen.getByText('TASK 4')).toBeInTheDocument();
    });

    it('truncates long descriptions correctly', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Long description should be truncated with ellipsis
      const longDesc = screen.getByText(/Create PostgreSQL tables and relationships/);
      expect(longDesc.textContent).toContain('...');
    });

    it('displays task IDs correctly', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Check that ID is displayed truncated
      expect(screen.getByText(/ID: task1/)).toBeInTheDocument();
      expect(screen.getByText(/ID: task2/)).toBeInTheDocument();
    });

    it('displays notes with proper formatting', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Check notes display
      expect(screen.getByText(/Remember to implement/)).toBeInTheDocument();
      expect(screen.getByText(/Use UUID for primary keys/)).toBeInTheDocument();
      expect(screen.getByText(/Waiting for DevOps/)).toBeInTheDocument();
      
      // Check null notes show dash
      const rows = screen.getAllByRole('row');
      const thirdTaskRow = rows[3]; // Header + 3 tasks
      expect(within(thirdTaskRow).getByText('—')).toBeInTheDocument();
    });

    it('formats dates correctly', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Date formatting depends on locale, so check for presence
      const dateElements = screen.getAllByText(/\d{1,2}\/\d{1,2}\/\d{4}/);
      expect(dateElements.length).toBeGreaterThan(0);
    });

    it('applies correct status styling', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const completedBadge = screen.getByText('completed');
      const inProgressBadge = screen.getByText('in progress');
      const pendingBadge = screen.getByText('pending');
      const blockedBadge = screen.getByText('blocked');

      expect(completedBadge).toHaveClass('status-badge', 'status-completed');
      expect(inProgressBadge).toHaveClass('status-badge', 'status-in_progress');
      expect(pendingBadge).toHaveClass('status-badge', 'status-pending');
      expect(blockedBadge).toHaveClass('status-badge', 'status-blocked');
    });

    it('handles empty data gracefully', () => {
      render(
        <TaskTable 
          data={[]}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Headers should still be present
      expect(screen.getByText('#')).toBeInTheDocument();
      expect(screen.getByText('Task Name')).toBeInTheDocument();
      
      // Check for "No tasks" message
      expect(screen.getByText('No tasks to display')).toBeInTheDocument();
    });
  });

  describe('Filtering', () => {
    it('filters tasks based on global filter', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter="authentication"
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Only authentication task should be visible
      expect(screen.getByText('Complete authentication system')).toBeInTheDocument();
      expect(screen.queryByText('Setup database schema')).not.toBeInTheDocument();
      expect(screen.queryByText('Write unit tests')).not.toBeInTheDocument();
    });

    it('shows no results message when filter matches nothing', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter="nonexistent"
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      expect(screen.getByText('No tasks to display')).toBeInTheDocument();
    });

    it('filter is case insensitive', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter="AUTHENTICATION"
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      expect(screen.getByText('Complete authentication system')).toBeInTheDocument();
    });

    it('filters by status', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter="completed"
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      expect(screen.getByText('Complete authentication system')).toBeInTheDocument();
      expect(screen.queryByText('Setup database schema')).not.toBeInTheDocument();
    });

    it('filters by notes content', () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter="UUID"
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      expect(screen.getByText('Setup database schema')).toBeInTheDocument();
      expect(screen.queryByText('Complete authentication system')).not.toBeInTheDocument();
    });
  });

  describe('Sorting', () => {
    it('sorts by column when header clicked', async () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const nameHeader = screen.getByText('Task Name');
      
      // Click to sort ascending
      fireEvent.click(nameHeader);
      
      await waitFor(() => {
        const rows = screen.getAllByRole('row');
        expect(within(rows[1]).getByText('Complete authentication system')).toBeInTheDocument();
      });

      // Click again to sort descending
      fireEvent.click(nameHeader);
      
      await waitFor(() => {
        const rows = screen.getAllByRole('row');
        expect(within(rows[1]).getByText('Write unit tests')).toBeInTheDocument();
      });
    });

    it('sorts by status correctly', async () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const statusHeader = screen.getByText('Status');
      fireEvent.click(statusHeader);

      await waitFor(() => {
        const statusBadges = screen.getAllByTestId(/status-badge/);
        // Check order: blocked, completed, in_progress, pending
        expect(statusBadges[0]).toHaveTextContent('blocked');
      });
    });

    it('sorts by date columns', async () => {
      render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const createdHeader = screen.getByText('Created');
      fireEvent.click(createdHeader);

      await waitFor(() => {
        const rows = screen.getAllByRole('row');
        // First data row should be the oldest task
        expect(within(rows[1]).getByText('Complete authentication system')).toBeInTheDocument();
      });
    });
  });

  describe('Pagination', () => {
    const manyTasks = Array.from({ length: 25 }, (_, i) => ({
      id: `task${i}`,
      name: `Task ${i}`,
      description: `Description ${i}`,
      status: i % 2 === 0 ? 'pending' : 'completed',
      createdAt: new Date(2025, 0, i + 1).toISOString(),
      updatedAt: new Date(2025, 0, i + 1).toISOString()
    }));

    it('displays pagination controls when data exceeds page size', () => {
      render(
        <TaskTable 
          data={manyTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      expect(screen.getByText(/Showing \d+ to \d+ of \d+ tasks/)).toBeInTheDocument();
      expect(screen.getByLabelText('First page')).toBeInTheDocument();
      expect(screen.getByLabelText('Previous page')).toBeInTheDocument();
      expect(screen.getByLabelText('Next page')).toBeInTheDocument();
      expect(screen.getByLabelText('Last page')).toBeInTheDocument();
    });

    it('navigates between pages correctly', async () => {
      render(
        <TaskTable 
          data={manyTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Initially on page 1
      expect(screen.getByText('Task 0')).toBeInTheDocument();
      expect(screen.queryByText('Task 10')).not.toBeInTheDocument();

      // Go to next page
      const nextButton = screen.getByLabelText('Next page');
      fireEvent.click(nextButton);

      await waitFor(() => {
        expect(screen.queryByText('Task 0')).not.toBeInTheDocument();
        expect(screen.getByText('Task 10')).toBeInTheDocument();
      });
    });

    it('disables navigation buttons appropriately', () => {
      render(
        <TaskTable 
          data={manyTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // On first page, previous buttons should be disabled
      expect(screen.getByLabelText('First page')).toBeDisabled();
      expect(screen.getByLabelText('Previous page')).toBeDisabled();
      expect(screen.getByLabelText('Next page')).not.toBeDisabled();
      expect(screen.getByLabelText('Last page')).not.toBeDisabled();
    });

    it('allows changing page size', async () => {
      render(
        <TaskTable 
          data={manyTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const pageSizeSelect = screen.getByRole('combobox');
      await userEvent.selectOptions(pageSizeSelect, '20');

      await waitFor(() => {
        expect(screen.getByText(/Showing 1 to 20 of 25 tasks/)).toBeInTheDocument();
      });
    });

    it('allows jumping to specific page', async () => {
      render(
        <TaskTable 
          data={manyTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const pageInput = screen.getByLabelText(/Go to page/);
      await userEvent.clear(pageInput);
      await userEvent.type(pageInput, '2{enter}');

      await waitFor(() => {
        expect(screen.getByText('Task 10')).toBeInTheDocument();
      });
    });
  });

  describe('Task Selection', () => {
    it('opens task detail view when row is clicked', async () => {
      const { container } = render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const firstRow = container.querySelector('tbody tr');
      fireEvent.click(firstRow);

      await waitFor(() => {
        expect(screen.getByText('← Back to Tasks')).toBeInTheDocument();
        expect(screen.getByText('Complete authentication system')).toBeInTheDocument();
      });
    });

    it('shows clickable cursor on hover', () => {
      const { container } = render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const rows = container.querySelectorAll('tbody tr');
      rows.forEach(row => {
        expect(row).toHaveStyle({ cursor: 'pointer' });
      });
    });
  });

  describe('Responsive Behavior', () => {
    it('adjusts column widths appropriately', () => {
      const { container } = render(
        <TaskTable 
          data={mockTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const table = container.querySelector('table');
      expect(table).toHaveClass('task-table');
    });

    it('handles long task names gracefully', () => {
      const longNameTask = {
        ...mockTasks[0],
        name: 'This is a very long task name that should be handled gracefully by the table component without breaking the layout'
      };

      render(
        <TaskTable 
          data={[longNameTask]}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      const taskName = screen.getByText(/This is a very long task name/);
      expect(taskName).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('handles tasks with missing fields', () => {
      const incompleteTask = {
        id: 'incomplete',
        name: 'Incomplete Task',
        // Missing other fields
      };

      render(
        <TaskTable 
          data={[incompleteTask]}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      expect(screen.getByText('Incomplete Task')).toBeInTheDocument();
      // Should show dashes for missing data
      const dashes = screen.getAllByText('—');
      expect(dashes.length).toBeGreaterThan(0);
    });

    it('handles very large datasets efficiently', () => {
      const largeTasks = Array.from({ length: 1000 }, (_, i) => ({
        id: `task${i}`,
        name: `Task ${i}`,
        description: `Description ${i}`,
        status: 'pending',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      }));

      const { container } = render(
        <TaskTable 
          data={largeTasks}
          globalFilter=""
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Should only render visible rows (10 by default)
      const rows = container.querySelectorAll('tbody tr');
      expect(rows.length).toBe(10);
    });

    it('preserves filter when data updates', () => {
      const { rerender } = render(
        <TaskTable 
          data={mockTasks}
          globalFilter="authentication"
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      expect(screen.getByText('Complete authentication system')).toBeInTheDocument();

      // Update with new data
      const newTasks = [...mockTasks, {
        id: 'task5',
        name: 'New authentication task',
        description: 'Another auth task',
        status: 'pending',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      }];

      rerender(
        <TaskTable 
          data={newTasks}
          globalFilter="authentication"
          onGlobalFilterChange={mockOnFilterChange}
        />
      );

      // Both authentication tasks should be visible
      expect(screen.getByText('Complete authentication system')).toBeInTheDocument();
      expect(screen.getByText('New authentication task')).toBeInTheDocument();
    });
  });
});