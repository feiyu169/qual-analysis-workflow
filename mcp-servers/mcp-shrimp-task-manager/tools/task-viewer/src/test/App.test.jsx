import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';

describe('App Component', () => {
  const mockProfiles = [
    { id: 'agent1', name: 'Agent 1', path: '/path/1' },
    { id: 'agent2', name: 'Agent 2', path: '/path/2' }
  ];

  const mockTasks = {
    tasks: [
      {
        id: '1',
        name: 'Task 1',
        description: 'Description 1',
        status: 'pending',
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z'
      },
      {
        id: '2',
        name: 'Task 2',
        description: 'Description 2',
        status: 'completed',
        createdAt: '2024-01-02T00:00:00Z',
        updatedAt: '2024-01-02T00:00:00Z'
      }
    ]
  };

  beforeEach(() => {
    fetch.mockClear();
    vi.clearAllMocks();
  });

  describe('Initial Load', () => {
    it('should load profiles on mount', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfiles
      });

      render(<App />);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith('/api/agents');
      });
    });

    it('should display error if profile loading fails', async () => {
      fetch.mockRejectedValueOnce(new Error('Network error'));

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(/Failed to load profiles/)).toBeInTheDocument();
      });
    });

    it('should show "No profiles" message when no profiles exist', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => []
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('No profiles configured')).toBeInTheDocument();
      });
    });
  });

  describe('Profile Management', () => {
    beforeEach(async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfiles
      });
    });

    it('should display profile tabs', async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Agent 1')).toBeInTheDocument();
        expect(screen.getByText('Agent 2')).toBeInTheDocument();
      });
    });

    it('should load tasks when profile is selected', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTasks
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Agent 1')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Agent 1'));

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/tasks/agent1'));
      });
    });

    it('should clear search when switching profiles', async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: async () => mockTasks
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Agent 1')).toBeInTheDocument();
      });

      // Select first profile and enter search
      fireEvent.click(screen.getByText('Agent 1'));
      const searchInput = await screen.findByPlaceholderText(/Search tasks/);
      await userEvent.type(searchInput, 'test search');

      // Switch to second profile
      fireEvent.click(screen.getByText('Agent 2'));

      await waitFor(() => {
        expect(searchInput.value).toBe('');
      });
    });

    it('should handle task loading errors', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Agent 1')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Agent 1'));

      await waitFor(() => {
        expect(screen.getByText(/Error loading tasks/)).toBeInTheDocument();
      });
    });
  });

  describe('Add Profile', () => {
    beforeEach(async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfiles
      });
    });

    it('should show add profile form when button clicked', async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('+ Add Profile')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('+ Add Profile'));

      expect(screen.getByText('Add New Profile')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Profile Name')).toBeInTheDocument();
    });

    it('should add new profile successfully', async () => {
      fetch
        .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'new-agent' }) })
        .mockResolvedValueOnce({ ok: true, json: async () => [...mockProfiles, { id: 'new-agent', name: 'New Agent' }] });

      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('+ Add Profile'));
      });

      const nameInput = screen.getByPlaceholderText('Profile Name');
      await userEvent.type(nameInput, 'New Agent');

      // Simulate file upload
      const file = new File(['{"tasks":[]}'], 'tasks.json', { type: 'application/json' });
      const fileInput = screen.getByLabelText(/JSON file/);
      await userEvent.upload(fileInput, file);

      fireEvent.click(screen.getByText('Add Profile'));

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith('/api/add-profile', expect.objectContaining({
          method: 'POST',
          body: expect.any(FormData)
        }));
      });
    });

    it('should show error if add profile fails', async () => {
      fetch.mockResolvedValueOnce({
        ok: false
      });

      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('+ Add Profile'));
      });

      const nameInput = screen.getByPlaceholderText('Profile Name');
      await userEvent.type(nameInput, 'New Agent');

      const file = new File(['{"tasks":[]}'], 'tasks.json', { type: 'application/json' });
      const fileInput = screen.getByLabelText(/JSON file/);
      await userEvent.upload(fileInput, file);

      fireEvent.click(screen.getByText('Add Profile'));

      await waitFor(() => {
        expect(screen.getByText(/Failed to add profile/)).toBeInTheDocument();
      });
    });

    it('should cancel add profile form', async () => {
      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('+ Add Profile'));
      });

      expect(screen.getByText('Add New Profile')).toBeInTheDocument();

      fireEvent.click(screen.getByText('Cancel'));

      expect(screen.queryByText('Add New Profile')).not.toBeInTheDocument();
    });
  });

  describe('Remove Profile', () => {
    beforeEach(async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfiles
      });
    });

    it('should confirm before removing profile', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Agent 1')).toBeInTheDocument();
      });

      const removeButton = screen.getAllByLabelText(/Remove profile/)[0];
      fireEvent.click(removeButton);

      expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('Are you sure'));
      expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining('/api/remove-profile'));
    });

    it('should remove profile when confirmed', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(true);

      fetch
        .mockResolvedValueOnce({ ok: true })
        .mockResolvedValueOnce({ ok: true, json: async () => [mockProfiles[1]] });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Agent 1')).toBeInTheDocument();
      });

      const removeButton = screen.getAllByLabelText(/Remove profile/)[0];
      fireEvent.click(removeButton);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith('/api/remove-profile/agent1', {
          method: 'DELETE'
        });
      });
    });

    it('should clear tasks if removing selected profile', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(true);

      fetch
        .mockResolvedValueOnce({ ok: true, json: async () => mockTasks })
        .mockResolvedValueOnce({ ok: true })
        .mockResolvedValueOnce({ ok: true, json: async () => [mockProfiles[1]] });

      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('Agent 1'));
      });

      await waitFor(() => {
        expect(screen.getByText('Task 1')).toBeInTheDocument();
      });

      const removeButton = screen.getAllByLabelText(/Remove profile/)[0];
      fireEvent.click(removeButton);

      await waitFor(() => {
        expect(screen.queryByText('Task 1')).not.toBeInTheDocument();
      });
    });
  });

  describe('Auto-refresh', () => {
    beforeEach(async () => {
      vi.useFakeTimers();
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfiles
      });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should enable auto-refresh', async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: async () => mockTasks
      });

      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('Agent 1'));
      });

      const autoRefreshCheckbox = screen.getByLabelText(/Auto-refresh/);
      fireEvent.click(autoRefreshCheckbox);

      expect(autoRefreshCheckbox).toBeChecked();

      // Fast-forward time
      vi.advanceTimersByTime(30000);

      await waitFor(() => {
        // Should have been called at least twice (initial + auto-refresh)
        expect(fetch.mock.calls.filter(call => call[0].includes('/api/tasks/')).length).toBeGreaterThanOrEqual(2);
      });
    });

    it('should update refresh interval', async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Agent 1')).toBeInTheDocument();
      });

      const intervalInput = screen.getByLabelText(/Refresh interval/);
      await userEvent.clear(intervalInput);
      await userEvent.type(intervalInput, '60');

      expect(intervalInput.value).toBe('60');
    });

    it('should stop auto-refresh when disabled', async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: async () => mockTasks
      });

      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('Agent 1'));
      });

      const autoRefreshCheckbox = screen.getByLabelText(/Auto-refresh/);
      
      // Enable
      fireEvent.click(autoRefreshCheckbox);
      expect(autoRefreshCheckbox).toBeChecked();

      // Disable
      fireEvent.click(autoRefreshCheckbox);
      expect(autoRefreshCheckbox).not.toBeChecked();

      // Fast-forward time
      vi.advanceTimersByTime(30000);

      // Should not have made additional calls
      expect(fetch).toHaveBeenCalledTimes(2); // Initial profiles + initial tasks
    });
  });

  describe('Manual Refresh', () => {
    beforeEach(async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfiles
      });
    });

    it('should refresh tasks when refresh button clicked', async () => {
      fetch
        .mockResolvedValueOnce({ ok: true, json: async () => mockTasks })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ ...mockTasks, tasks: [...mockTasks.tasks, { id: '3', name: 'Task 3' }] }) });

      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('Agent 1'));
      });

      await waitFor(() => {
        expect(screen.getByText('Task 1')).toBeInTheDocument();
      });

      const refreshButton = screen.getByLabelText('Refresh tasks');
      fireEvent.click(refreshButton);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/tasks/agent1'));
      });
    });

    it('should show loading state during refresh', async () => {
      fetch.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(<App />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('Agent 1'));
      });

      expect(screen.getByText('Loading tasks...')).toBeInTheDocument();
    });
  });

  describe('Error States', () => {
    it('should display network error gracefully', async () => {
      fetch.mockRejectedValueOnce(new Error('Network failure'));

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(/Failed to load profiles.*Network failure/)).toBeInTheDocument();
      });
    });

    it('should handle JSON parse errors', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => { throw new Error('Invalid JSON'); }
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(/Failed to load profiles.*Invalid JSON/)).toBeInTheDocument();
      });
    });
  });
});