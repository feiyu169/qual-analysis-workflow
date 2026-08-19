#!/usr/bin/env node

const http = require('http');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');

// Version information
const VERSION = '1.0.0';
const PORT = process.env.SHRIMP_VIEWER_PORT || 9998;
const SETTINGS_FILE = path.join(os.homedir(), '.shrimp-task-viewer-settings.json');

// Default agent data paths configuration (can be customized per installation)
const defaultAgents = [
    // Example: { id: 'project1', name: 'My Project Tasks', path: '/path/to/project/shrimp_data/tasks.json' }
    // Add your default task file paths here, or use the web interface to add profiles
];

let agents = [];

// Load or create settings file
async function loadSettings() {
    try {
        console.log('Loading settings from:', SETTINGS_FILE);
        const data = await fs.readFile(SETTINGS_FILE, 'utf8');
        const settings = JSON.parse(data);
        console.log('Loaded settings:', settings);
        return settings.agents || [];
    } catch (err) {
        console.error('Error loading settings:', err.message);
        // File doesn't exist, create with defaults
        await saveSettings(defaultAgents);
        return defaultAgents;
    }
}

// Save settings file
async function saveSettings(agentList) {
    const settings = {
        agents: agentList,
        lastUpdated: new Date().toISOString(),
        version: VERSION
    };
    await fs.writeFile(SETTINGS_FILE, JSON.stringify(settings, null, 2));
}

// Add new agent
async function addAgent(name, filePath) {
    const id = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-');
    const newAgent = { id, name, path: filePath };
    
    // Check if agent already exists
    const existingIndex = agents.findIndex(a => a.id === id);
    if (existingIndex >= 0) {
        agents[existingIndex] = newAgent;
    } else {
        agents.push(newAgent);
    }
    
    await saveSettings(agents);
    return newAgent;
}

// Remove agent
async function removeAgent(agentId) {
    agents = agents.filter(a => a.id !== agentId);
    await saveSettings(agents);
}

// Enhanced HTML with real data fetching
const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shrimp Task Manager Viewer v${VERSION}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🦐</text></svg>">
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background: #1a1a2e;
            color: #eee;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 {
            color: #4fbdba;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
        .version-info {
            text-align: center;
            color: #666;
            font-size: 0.9rem;
            margin-top: -20px;
            margin-bottom: 30px;
        }
        .agent-selector {
            text-align: center;
            margin-bottom: 30px;
        }
        .agent-selector select {
            padding: 10px 20px;
            font-size: 16px;
            background: #16213e;
            color: #eee;
            border: 2px solid #0f4c75;
            border-radius: 5px;
            cursor: pointer;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #16213e;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .stat-card h3 {
            margin: 0 0 10px 0;
            color: #0f4c75;
        }
        .stat-card .value {
            font-size: 2rem;
            font-weight: bold;
            color: #4fbdba;
        }
        .filter-controls {
            margin-bottom: 20px;
        }
        .search-container {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
            align-items: center;
            flex-wrap: wrap;
        }
        .filter-buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            flex-wrap: wrap;
        }
        #searchBox {
            flex: 1;
            min-width: 200px;
            padding: 10px 15px;
            border: 2px solid #2c3e50;
            border-radius: 25px;
            background: #1a252f;
            color: white;
            font-size: 1rem;
        }
        #searchBox:focus {
            outline: none;
            border-color: #4fbdba;
        }
        .auto-refresh-toggle {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #aaa;
            cursor: pointer;
            white-space: nowrap;
        }
        .auto-refresh-toggle input[type="checkbox"] {
            transform: scale(1.2);
        }
        .filter-btn {
            padding: 8px 20px;
            background: #16213e;
            border: 2px solid #0f4c75;
            color: #eee;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .filter-btn:hover, .filter-btn.active {
            background: #0f4c75;
            color: white;
        }
        .tasks-grid {
            display: grid;
            gap: 20px;
        }
        .task-card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .task-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.4);
        }
        .task-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
            gap: 10px;
        }
        .task-number {
            background: #0f4c75;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
            white-space: nowrap;
        }
        .task-title {
            font-size: 1.2rem;
            font-weight: bold;
            color: #4fbdba;
            margin: 0;
            flex: 1;
        }
        .task-status {
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-pending {
            background: #e74c3c;
            color: white;
        }
        .status-in_progress {
            background: #f39c12;
            color: white;
        }
        .status-completed {
            background: #27ae60;
            color: white;
        }
        .task-meta {
            display: flex;
            gap: 20px;
            margin-bottom: 10px;
            font-size: 0.9rem;
            color: #aaa;
            flex-wrap: wrap;
        }
        .task-description {
            color: #ddd;
            line-height: 1.6;
            margin-bottom: 15px;
        }
        .task-notes {
            background: #0f3460;
            padding: 10px;
            border-radius: 5px;
            font-style: italic;
            color: #aaa;
            margin-bottom: 15px;
        }
        .task-files {
            margin-top: 15px;
        }
        .task-files h4 {
            margin: 0 0 10px 0;
            color: #0f4c75;
        }
        .file-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 5px 0;
            font-size: 0.9rem;
        }
        .file-type {
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8rem;
            font-weight: bold;
        }
        .type-TO_MODIFY {
            background: #e67e22;
            color: white;
        }
        .type-REFERENCE {
            background: #3498db;
            color: white;
        }
        .type-CREATE {
            background: #2ecc71;
            color: white;
        }
        .type-DEPENDENCY {
            background: #9b59b6;
            color: white;
        }
        .loading {
            text-align: center;
            padding: 50px;
            font-size: 1.2rem;
        }
        .loading.with-spinner::after {
            content: ' ⏳';
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        .error {
            background: #e74c3c;
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            margin: 20px 0;
        }
        .summary-section {
            background: #0f3460;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
        }
        .summary-section h4 {
            margin: 0 0 10px 0;
            color: #4fbdba;
        }
        .task-id {
            font-family: monospace;
            font-size: 0.8rem;
            color: #666;
        }
        .refresh-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 15px 25px;
            background: #0f4c75;
            color: white;
            border: none;
            border-radius: 50px;
            cursor: pointer;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            font-size: 1rem;
            transition: all 0.3s;
        }
        .refresh-btn:hover {
            background: #4fbdba;
            transform: scale(1.05);
        }
        .manage-btn {
            margin-left: 15px;
            padding: 8px 15px;
            background: #4fbdba;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.3s;
        }
        .manage-btn:hover {
            background: #0f4c75;
        }
        .management-panel {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .management-content {
            background: #1a1a2e;
            border-radius: 15px;
            padding: 30px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            border: 2px solid #4fbdba;
        }
        .management-content h3 {
            color: #4fbdba;
            margin-top: 0;
            text-align: center;
        }
        .management-content h4 {
            color: #0f4c75;
            border-bottom: 1px solid #0f4c75;
            padding-bottom: 10px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: #eee;
            font-weight: bold;
        }
        .form-group input[type="text"] {
            width: 100%;
            padding: 10px;
            background: #16213e;
            border: 2px solid #0f4c75;
            border-radius: 5px;
            color: #eee;
            font-size: 14px;
        }
        .form-group input[type="file"] {
            width: 100%;
            padding: 10px;
            background: #16213e;
            border: 2px solid #0f4c75;
            border-radius: 5px;
            color: #eee;
            cursor: pointer;
        }
        .file-info {
            margin-top: 10px;
            padding: 10px;
            background: #0f3460;
            border-radius: 5px;
            font-size: 0.9rem;
            color: #aaa;
        }
        .add-btn, .close-btn {
            padding: 12px 25px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1rem;
            margin: 10px 5px;
            transition: all 0.3s;
        }
        .add-btn {
            background: #27ae60;
            color: white;
        }
        .add-btn:hover {
            background: #2ecc71;
        }
        .close-btn {
            background: #e74c3c;
            color: white;
            float: right;
        }
        .close-btn:hover {
            background: #c0392b;
        }
        .profiles-list {
            max-height: 200px;
            overflow-y: auto;
        }
        .profile-item {
            background: #16213e;
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .profile-info {
            flex: 1;
        }
        .profile-name {
            color: #4fbdba;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .profile-path {
            color: #aaa;
            font-size: 0.8rem;
            font-family: monospace;
        }
        .remove-btn {
            background: #e74c3c;
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.8rem;
        }
        .remove-btn:hover {
            background: #c0392b;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🦐 Shrimp Task Manager Viewer</h1>
        <div class="version-info">Version ${VERSION} - Universal Profile Management<br>
            <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager" target="_blank" style="color: #4fbdba; text-decoration: none;">📁 GitHub Repository</a>
        </div>
        
        <div class="agent-selector">
            <label for="agent">Select Profile: </label>
            <select id="agent">
                <option value="">Select a profile...</option>
            </select>
            <button class="manage-btn" id="manageBtn">⚙️ Manage Profiles</button>
        </div>

        <div id="management" class="management-panel" style="display: none;">
            <div class="management-content">
                <h3>🗂️ Profile Management</h3>
                
                <div class="add-profile-section">
                    <h4>Add New Profile</h4>
                    <div class="form-group">
                        <label for="profileName">Profile Name:</label>
                        <input type="text" id="profileName" placeholder="e.g., My Project Tasks" />
                    </div>
                    <div class="form-group">
                        <label for="taskFile">Select tasks.json file:</label>
                        <input type="file" id="taskFile" accept=".json" />
                        <div class="file-info" id="fileInfo" style="display: none;"></div>
                    </div>
                    <button id="addBtn" class="add-btn">➕ Add Profile</button>
                </div>

                <div class="existing-profiles-section">
                    <h4>Existing Profiles</h4>
                    <div id="profilesList" class="profiles-list"></div>
                </div>

                <button id="closeBtn" class="close-btn">✖️ Close</button>
            </div>
        </div>

        <div id="stats" class="stats" style="display: none;">
            <div class="stat-card">
                <h3>Total Tasks</h3>
                <div class="value" id="totalTasks">0</div>
            </div>
            <div class="stat-card">
                <h3>Completed</h3>
                <div class="value" id="completedTasks">0</div>
            </div>
            <div class="stat-card">
                <h3>In Progress</h3>
                <div class="value" id="inProgressTasks">0</div>
            </div>
            <div class="stat-card">
                <h3>Pending</h3>
                <div class="value" id="pendingTasks">0</div>
            </div>
        </div>

        <div id="filterControls" class="filter-controls" style="display: none;">
            <div class="search-container">
                <input type="text" id="searchBox" placeholder="🔍 Search tasks..." oninput="filterTasksBySearch(this.value)" />
                <label class="auto-refresh-toggle">
                    <input type="checkbox" id="autoRefresh" onchange="toggleAutoRefresh(this.checked)" />
                    Auto-refresh (30s)
                </label>
            </div>
            <div class="filter-buttons">
                <button class="filter-btn active" data-filter="all">All Tasks</button>
                <button class="filter-btn" data-filter="completed">Completed</button>
            <button class="filter-btn" data-filter="in_progress">In Progress</button>
            <button class="filter-btn" data-filter="pending">Pending</button>
            </div>
        </div>

        <div id="loading" class="loading">Select a profile to view tasks...</div>
        <div id="error" class="error" style="display: none;"></div>
        <div id="tasks" class="tasks-grid" style="display: none;"></div>
    </div>

    <button class="refresh-btn" id="refreshBtn">🔄 Refresh</button>

    <script>
        let currentTasks = [];
        let filteredTasks = [];
        let currentFilter = 'all';

        // Profile management functions
        function toggleManagement() {
            const panel = document.getElementById('management');
            console.log('Toggle management called, current display:', panel.style.display);
            if (panel.style.display === 'none' || panel.style.display === '') {
                panel.style.display = 'flex';
                loadProfilesList();
                console.log('Management panel opened');
            } else {
                panel.style.display = 'none';
                console.log('Management panel closed');
            }
        }

        async function loadProfilesList() {
            try {
                const response = await fetch('/api/agents');
                const agents = await response.json();
                
                const container = document.getElementById('profilesList');
                container.innerHTML = agents.map(agent => 
                    '<div class="profile-item">' +
                        '<div class="profile-info">' +
                            '<div class="profile-name">' + escapeHtml(agent.name) + '</div>' +
                            '<div class="profile-path">' + escapeHtml(agent.path) + '</div>' +
                        '</div>' +
                        '<button class="remove-btn" data-agent-id="' + agent.id + '">🗑️ Remove</button>' +
                    '</div>'
                ).join('');
                
                // Add event listeners to remove buttons
                document.querySelectorAll('.remove-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        removeProfile(this.getAttribute('data-agent-id'));
                    });
                });
            } catch (err) {
                console.error('Error loading profiles:', err);
            }
        }

        async function addProfile() {
            const nameInput = document.getElementById('profileName');
            const fileInput = document.getElementById('taskFile');
            
            const name = nameInput.value.trim();
            const file = fileInput.files[0];
            
            if (!name) {
                alert('Please enter a profile name');
                return;
            }
            
            if (!file) {
                alert('Please select a tasks.json file');
                return;
            }

            try {
                // Read file content to validate it's a valid tasks.json
                const fileContent = await file.text();
                const taskData = JSON.parse(fileContent);
                
                if (!taskData.tasks || !Array.isArray(taskData.tasks)) {
                    alert('Invalid tasks.json file. Must contain a "tasks" array.');
                    return;
                }

                // Create FormData to send file content as text
                const formData = new FormData();
                formData.append('name', name);
                formData.append('taskFile', fileContent);

                const response = await fetch('/api/add-profile', {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    nameInput.value = '';
                    fileInput.value = '';
                    document.getElementById('fileInfo').style.display = 'none';
                    
                    // Reload agents and profiles list
                    await loadAgents();
                    await loadProfilesList();
                    
                    alert('Profile added successfully!');
                } else {
                    const error = await response.text();
                    alert('Error adding profile: ' + error);
                }
            } catch (err) {
                alert('Error processing file: ' + err.message);
            }
        }

        async function removeProfile(agentId) {
            if (!confirm('Are you sure you want to remove this profile?')) {
                return;
            }

            try {
                const response = await fetch('/api/remove-profile/' + agentId, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    await loadAgents();
                    await loadProfilesList();
                    
                    // Clear selection if removed profile was selected
                    const agentSelect = document.getElementById('agent');
                    if (agentSelect.value === agentId) {
                        agentSelect.value = '';
                        document.getElementById('tasks').style.display = 'none';
                        document.getElementById('stats').style.display = 'none';
                        document.getElementById('filterControls').style.display = 'none';
                    }
                } else {
                    const error = await response.text();
                    alert('Error removing profile: ' + error);
                }
            } catch (err) {
                alert('Error removing profile: ' + err.message);
            }
        }

        async function loadAgents() {
            try {
                console.log('Loading agents...');
                const response = await fetch('/api/agents');
                console.log('Response status:', response.status);
                const agents = await response.json();
                console.log('Agents loaded:', agents);
                
                const select = document.getElementById('agent');
                select.innerHTML = '<option value="">Select a profile...</option>' + 
                    agents.map(agent => 
                        '<option value="' + agent.id + '">' + agent.name + '</option>'
                    ).join('');
                
                console.log('Dropdown updated with', agents.length, 'agents');
                
            } catch (err) {
                console.error('Error loading agents:', err);
                const error = document.getElementById('error');
                error.textContent = 'Error loading agents: ' + err.message;
                error.style.display = 'block';
            }
        }

        async function loadTasks() {
            const agentId = document.getElementById('agent').value;
            if (!agentId) return;

            const loading = document.getElementById('loading');
            const error = document.getElementById('error');
            const tasksContainer = document.getElementById('tasks');
            const stats = document.getElementById('stats');
            const filterControls = document.getElementById('filterControls');

            loading.style.display = 'block';
            loading.textContent = 'Loading tasks... ⏳';
            loading.className = 'loading with-spinner';
            error.style.display = 'none';
            tasksContainer.style.display = 'none';
            stats.style.display = 'none';
            filterControls.style.display = 'none';

            try {
                console.log('Loading tasks for agent:', agentId);
                // Add timestamp to bypass cache
                const response = await fetch('/api/tasks/' + agentId + '?t=' + Date.now());
                console.log('Response status:', response.status);
                
                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('Response error:', errorText);
                    throw new Error('Failed to load tasks: ' + response.status + ' - ' + errorText);
                }
                
                const data = await response.json();
                console.log('Received data:', data);
                currentTasks = data.tasks || [];
                console.log('Current tasks:', currentTasks.length);
                
                // Keep original order from tasks.json to match CLI numbering
                // Comment out sorting to preserve task numbers
                // currentTasks.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
                
                filterTasks(currentFilter);
                updateStats();

                loading.style.display = 'none';
                loading.className = 'loading';
                tasksContainer.style.display = 'grid';
                stats.style.display = 'grid';
                filterControls.style.display = 'block';

            } catch (err) {
                loading.style.display = 'none';
                loading.className = 'loading';
                error.style.display = 'block';
                error.textContent = '❌ Error loading tasks: ' + err.message;
            }
        }

        function filterTasks(filter, buttonElement) {
            currentFilter = filter;
            
            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Add active class to the clicked button or find it by filter
            if (buttonElement) {
                buttonElement.classList.add('active');
            } else {
                // Find button by filter value when called programmatically
                const buttons = document.querySelectorAll('.filter-btn');
                buttons.forEach(btn => {
                    if (btn.textContent.toLowerCase().includes(filter) || 
                        (filter === 'all' && btn.textContent.includes('All'))) {
                        btn.classList.add('active');
                    }
                });
            }
            
            applyFilters();
        }

        function displayTasks() {
            const container = document.getElementById('tasks');
            
            if (filteredTasks.length === 0) {
                container.innerHTML = '<div class="loading">No tasks found</div>';
                return;
            }
            
            container.innerHTML = filteredTasks.map(task => {
                const createdDate = new Date(task.createdAt).toLocaleDateString() + ' ' + 
                                   new Date(task.createdAt).toLocaleTimeString();
                const updatedDate = new Date(task.updatedAt).toLocaleDateString() + ' ' + 
                                   new Date(task.updatedAt).toLocaleTimeString();
                
                // Find the task number based on its position in the original array
                const taskNumber = currentTasks.findIndex(t => t.id === task.id) + 1;
                
                return '<div class="task-card">' +
                    '<div class="task-header">' +
                        '<span class="task-number">TASK ' + taskNumber + '</span>' +
                        '<h3 class="task-title">' + escapeHtml(task.name) + '</h3>' +
                        '<span class="task-status status-' + task.status + '">' + task.status.replace('_', ' ') + '</span>' +
                    '</div>' +
                    
                    '<div class="task-id">ID: ' + task.id + '</div>' +
                    
                    '<div class="task-meta">' +
                        '<span>Created: ' + createdDate + '</span>' +
                        '<span>Updated: ' + updatedDate + '</span>' +
                    '</div>' +
                    
                    '<div class="task-description">' + escapeHtml(task.description) + '</div>' +
                    
                    (task.notes ? '<div class="task-notes">' + escapeHtml(task.notes) + '</div>' : '') +
                    
                    (task.summary ? 
                        '<div class="summary-section">' +
                            '<h4>Summary</h4>' +
                            '<div>' + escapeHtml(task.summary) + '</div>' +
                        '</div>' 
                    : '') +
                    
                    (task.relatedFiles && task.relatedFiles.length > 0 ? 
                        '<div class="task-files">' +
                            '<h4>Related Files (' + task.relatedFiles.length + ')</h4>' +
                            task.relatedFiles.map(file => 
                                '<div class="file-item">' +
                                    '<span class="file-type type-' + file.type + '">' + file.type + '</span>' +
                                    '<span>' + escapeHtml(file.path) + 
                                    (file.lineStart ? ' (lines ' + file.lineStart + '-' + file.lineEnd + ')' : '') + 
                                    '</span>' +
                                '</div>'
                            ).join('') +
                        '</div>' 
                    : '') +
                '</div>';
            }).join('');
        }

        // Global variables for search and auto-refresh
        let currentSearchTerm = '';
        let autoRefreshInterval = null;

        function filterTasksBySearch(searchTerm) {
            currentSearchTerm = searchTerm.toLowerCase();
            applyFilters();
        }

        function applyFilters() {
            let tasks = currentTasks;
            
            // Apply status filter
            if (currentFilter !== 'all') {
                tasks = tasks.filter(task => task.status === currentFilter);
            }
            
            // Apply search filter
            if (currentSearchTerm.trim()) {
                tasks = tasks.filter(task => {
                    const searchableText = (
                        task.name + ' ' + 
                        task.description + ' ' + 
                        (task.notes || '') + ' ' +
                        task.status + ' ' +
                        task.id
                    ).toLowerCase();
                    return searchableText.includes(currentSearchTerm);
                });
            }
            
            filteredTasks = tasks;
            displayTasks();
        }

        function toggleAutoRefresh(enabled) {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
            
            if (enabled) {
                // Refresh every 30 seconds
                autoRefreshInterval = setInterval(() => {
                    const agentId = document.getElementById('agent').value;
                    if (agentId) {
                        console.log('Auto-refreshing tasks...');
                        loadTasks();
                    }
                }, 30000);
                console.log('Auto-refresh enabled (30s intervals)');
            } else {
                console.log('Auto-refresh disabled');
            }
        }

        function updateStats() {
            const stats = {
                total: currentTasks.length,
                completed: currentTasks.filter(t => t.status === 'completed').length,
                inProgress: currentTasks.filter(t => t.status === 'in_progress').length,
                pending: currentTasks.filter(t => t.status === 'pending').length
            };

            document.getElementById('totalTasks').textContent = stats.total;
            document.getElementById('completedTasks').textContent = stats.completed;
            document.getElementById('inProgressTasks').textContent = stats.inProgress;
            document.getElementById('pendingTasks').textContent = stats.pending;
        }

        function escapeHtml(text) {
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return (text || '').replace(/[&<>"']/g, m => map[m]);
        }

        // Handle file selection
        document.addEventListener('DOMContentLoaded', function() {
            const fileInput = document.getElementById('taskFile');
            fileInput?.addEventListener('change', function(e) {
                const file = e.target.files[0];
                const fileInfo = document.getElementById('fileInfo');
                
                if (file) {
                    fileInfo.innerHTML = 
                        '<strong>Selected:</strong> ' + escapeHtml(file.name) + '<br>' +
                        '<strong>Size:</strong> ' + (file.size / 1024).toFixed(1) + ' KB<br>' +
                        '<strong>Path:</strong> ' + escapeHtml(file.webkitRelativePath || file.name);
                    fileInfo.style.display = 'block';
                } else {
                    fileInfo.style.display = 'none';
                }
            });
        });

        // Initialize on page load
        window.onload = function() {
            console.log('Page loaded, initializing...');
            loadAgents();
        };

        // Setup event listeners when DOM is ready
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM Content Loaded, setting up event listeners...');
            
            // Management button
            const manageBtn = document.getElementById('manageBtn');
            if (manageBtn) {
                manageBtn.addEventListener('click', toggleManagement);
                console.log('Management button listener added');
            }
            
            // Add profile button
            const addBtn = document.getElementById('addBtn');
            if (addBtn) {
                addBtn.addEventListener('click', addProfile);
                console.log('Add button listener added');
            }
            
            // Close button
            const closeBtn = document.getElementById('closeBtn');
            if (closeBtn) {
                closeBtn.addEventListener('click', toggleManagement);
                console.log('Close button listener added');
            }
            
            // Agent selector
            const agentSelect = document.getElementById('agent');
            if (agentSelect) {
                agentSelect.addEventListener('change', loadTasks);
                console.log('Agent selector listener added');
            }
            
            // Refresh button
            const refreshBtn = document.getElementById('refreshBtn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', loadTasks);
                console.log('Refresh button listener added');
            }
            
            // Filter buttons
            document.addEventListener('click', function(e) {
                if (e.target.classList.contains('filter-btn')) {
                    const filter = e.target.getAttribute('data-filter');
                    filterTasks(filter, e.target);
                }
            });
            
            console.log('All event listeners set up successfully');
        });
    </script>
</body>
</html>`;

// Parse multipart form data
function parseMultipart(req) {
    return new Promise((resolve, reject) => {
        const boundary = req.headers['content-type']?.split('boundary=')[1];
        if (!boundary) {
            reject(new Error('No boundary found'));
            return;
        }

        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', () => {
            const parts = body.split('--' + boundary);
            const result = {};
            
            for (const part of parts) {
                if (part.includes('Content-Disposition')) {
                    const nameMatch = part.match(/name="([^"]+)"/);
                    if (nameMatch) {
                        const name = nameMatch[1];
                        const content = part.split('\r\n\r\n')[1]?.split('\r\n--')[0];
                        if (content) {
                            result[name] = content;
                        }
                    }
                }
            }
            resolve(result);
        });
        req.on('error', reject);
    });
}

// Create server
const server = http.createServer(async (req, res) => {
    console.log(`Request: ${req.method} ${req.url}`);

    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(htmlContent);
    } else if (req.url === '/api/agents') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(agents));
    } else if (req.url === '/api/add-profile' && req.method === 'POST') {
        try {
            const formData = await parseMultipart(req);
            const name = formData.name?.trim();
            const taskFileContent = formData.taskFile;
            
            if (!name || !taskFileContent) {
                res.writeHead(400, { 'Content-Type': 'text/plain' });
                res.end('Missing name or task file content');
                return;
            }

            // Validate JSON
            let taskData;
            try {
                taskData = JSON.parse(taskFileContent);
            } catch (err) {
                res.writeHead(400, { 'Content-Type': 'text/plain' });
                res.end('Invalid JSON in task file');
                return;
            }

            if (!taskData.tasks || !Array.isArray(taskData.tasks)) {
                res.writeHead(400, { 'Content-Type': 'text/plain' });
                res.end('Invalid tasks.json format - must contain tasks array');
                return;
            }

            // Create a file in user's home directory for this profile
            const userDataDir = path.join(os.homedir(), '.shrimp-task-viewer-data');
            await fs.mkdir(userDataDir, { recursive: true });
            
            const profileId = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-');
            const profileFilePath = path.join(userDataDir, `${profileId}.json`);
            
            // Save the task data
            await fs.writeFile(profileFilePath, taskFileContent);
            
            // Add to agents list
            const newAgent = await addAgent(name, profileFilePath);
            
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(newAgent));
        } catch (err) {
            console.error('Error adding profile:', err);
            res.writeHead(500, { 'Content-Type': 'text/plain' });
            res.end('Internal server error: ' + err.message);
        }
    } else if (req.url.startsWith('/api/remove-profile/') && req.method === 'DELETE') {
        try {
            const agentId = req.url.split('/').pop();
            const agent = agents.find(a => a.id === agentId);
            
            if (!agent) {
                res.writeHead(404, { 'Content-Type': 'text/plain' });
                res.end('Profile not found');
                return;
            }

            // Remove file if it's in user data directory
            const userDataDir = path.join(os.homedir(), '.shrimp-task-viewer-data');
            if (agent.path.startsWith(userDataDir)) {
                try {
                    await fs.unlink(agent.path);
                } catch (err) {
                    console.warn('Could not delete profile file:', err.message);
                }
            }

            // Remove from agents list
            await removeAgent(agentId);
            
            res.writeHead(200, { 'Content-Type': 'text/plain' });
            res.end('Profile removed successfully');
        } catch (err) {
            console.error('Error removing profile:', err);
            res.writeHead(500, { 'Content-Type': 'text/plain' });
            res.end('Internal server error: ' + err.message);
        }
    } else if (req.url === '/api/refresh' && req.method === 'POST') {
        // Reload settings from disk
        try {
            agents = await loadSettings();
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ message: 'Settings reloaded', agents: agents.length }));
        } catch (err) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Failed to reload settings' }));
        }
    } else if (req.url.startsWith('/api/tasks/')) {
        // Extract agentId and remove query parameters
        const urlParts = req.url.split('?')[0].split('/');
        const agentId = urlParts.pop();
        const agent = agents.find(a => a.id === agentId);
        
        if (!agent) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Agent not found' }));
            return;
        }

        try {
            const data = await fs.readFile(agent.path, 'utf8');
            res.writeHead(200, { 
                'Content-Type': 'application/json',
                'Cache-Control': 'no-store, no-cache, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            });
            res.end(data);
        } catch (err) {
            console.error(`Error reading file ${agent.path}:`, err);
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Tasks file not found', details: err.message }));
        }
    } else {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('Not Found');
    }
});

// Initialize server with settings
async function startServer() {
    try {
        agents = await loadSettings();
        
        server.listen(PORT, '127.0.0.1', () => {
            console.log(`
🦐 Shrimp Task Manager Viewer Server v${VERSION}
===============================================
Server is running at: http://localhost:${PORT}
Also accessible at: http://127.0.0.1:${PORT}

Settings file: ${SETTINGS_FILE}
    
Available profiles:
${agents.map(a => `  - ${a.name} (${a.path})`).join('\n')}

🎯 Features:
  • View tasks from multiple profiles
  • Add custom task files via web interface
  • Persistent profile management
  • Real-time task filtering and statistics

Open your browser to view tasks!
            `);
        });
    } catch (err) {
        console.error('Failed to start server:', err);
        process.exit(1);
    }
}

// Start the server
startServer();

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log('\nShutting down server...');
    server.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
});