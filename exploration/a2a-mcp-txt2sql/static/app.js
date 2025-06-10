// JavaScript for SQL Chat AI Frontend

class ChatApp {
    constructor() {
        this.threadId = this.generateThreadId();
        this.isLoading = false;
        
        // DOM elements
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.loadingIndicator = document.getElementById('loadingIndicator');
        this.statusIndicator = document.getElementById('status');
        this.exampleQueries = document.getElementById('exampleQueries');
        this.agentLegend = document.getElementById('agentLegend');
        this.agentOverlay = document.getElementById('agentOverlay');
        this.agentToggle = document.getElementById('agentToggle');
        this.closeAgents = document.getElementById('closeAgents');
        
        this.initializeEventListeners();
        this.checkServerHealth();
        this.initializeAgentLegend();
    }
    
    generateThreadId() {
        return 'thread_' + Math.random().toString(36).substr(2, 9);
    }
    
    initializeEventListeners() {
        // Send button click
        this.sendButton.addEventListener('click', () => this.sendMessage());
        
        // Enter key in input
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !this.isLoading) {
                this.sendMessage();
            }
        });
        
        // Example query clicks
        document.querySelectorAll('.example-query').forEach(element => {
            element.addEventListener('click', () => {
                const query = element.getAttribute('data-query');
                this.messageInput.value = query;
                this.sendMessage();
            });
        });
        
        // Agent overlay toggle
        this.agentToggle.addEventListener('click', () => {
            this.showAgentOverlay();
        });
        
        // Close agent overlay
        this.closeAgents.addEventListener('click', () => {
            this.hideAgentOverlay();
        });
        
        // Close overlay when clicking outside
        this.agentOverlay.addEventListener('click', (e) => {
            if (e.target === this.agentOverlay) {
                this.hideAgentOverlay();
            }
        });
    }
    
    async checkServerHealth() {
        try {
            const response = await fetch('/api/health');
            const health = await response.json();
            
            if (health.status === 'healthy') {
                this.updateStatus('connected', 'Connected');
                this.enableInput();
            } else {
                this.updateStatus('error', 'Server Degraded');
                console.warn('Server health check failed:', health);
            }
        } catch (error) {
            this.updateStatus('error', 'Connection Failed');
            console.error('Health check failed:', error);
        }
    }
    
    updateStatus(status, text) {
        this.statusIndicator.className = `status-indicator ${status}`;
        this.statusIndicator.querySelector('.status-text').textContent = text;
    }
    
    enableInput() {
        this.messageInput.disabled = false;
        this.sendButton.disabled = false;
    }
    
    disableInput() {
        this.messageInput.disabled = true;
        this.sendButton.disabled = true;
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isLoading) return;
        
        // Hide example queries after first message
        this.exampleQueries.style.display = 'none';
        
        // Add user message to chat
        this.addMessage('user', message);
        
        // Clear input and show loading
        this.messageInput.value = '';
        this.setLoading(true);
        
        // Show agents as potentially in-use during processing
        this.showActiveAgents(['general']);
        
        try {
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    thread_id: this.threadId
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            // Add assistant response to chat
            // Only show SQL query if SQL-related MCP servers or agents were actually used
            const usedSqlComponents = result.mcp_servers_used?.includes('sqlite_mcp_direct') || 
                                    result.agents_used?.includes('sql_validation_agent');
            this.addMessage('assistant', result.response, usedSqlComponents ? result.sql_query : null);
            
            // Update agent states based on response
            this.updateAgentsFromResponse(result);
            
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessage('assistant', `Sorry, I encountered an error: ${error.message}`, null, true);
            // Reset to general on error
            this.resetAgentStates();
            this.setAgentState('general', 'active');
        } finally {
            this.setLoading(false);
        }
    }
    
    addMessage(role, content, sqlQuery = null, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message`;
        
        const avatar = role === 'user' ? '🧑' : '🎵';
        
        messageDiv.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content ${isError ? 'error' : ''}">
                <div class="message-text">${this.formatMessage(content)}</div>
                ${sqlQuery ? this.formatSqlQuery(sqlQuery) : ''}
            </div>
        `;
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    formatMessage(content) {
        // Simple formatting for better readability
        return content
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
    }
    
    formatSqlQuery(sqlQuery) {
        return `
            <div class="sql-query">
                <div class="sql-query-header">🔍 Generated SQL Query:</div>
                <pre><code>${this.escapeHtml(sqlQuery)}</code></pre>
            </div>
        `;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    setLoading(loading) {
        this.isLoading = loading;
        
        if (loading) {
            this.loadingIndicator.style.display = 'flex';
            this.disableInput();
        } else {
            this.loadingIndicator.style.display = 'none';
            this.enableInput();
        }
    }
    
    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    initializeAgentLegend() {
        // Set all agents to inactive state initially
        this.resetAgentStates();
        
        // Mark general as active by default
        this.setAgentState('general', 'active');
    }
    
    resetAgentStates() {
        const agentItems = document.querySelectorAll('.agent-item');
        agentItems.forEach(item => {
            item.classList.remove('active', 'in-use');
        });
    }
    
    setAgentState(agentName, state) {
        const agentItem = document.querySelector(`[data-agent="${agentName}"]`);
        if (agentItem) {
            agentItem.classList.remove('active', 'in-use');
            if (state === 'active') {
                agentItem.classList.add('active');
            } else if (state === 'in-use') {
                agentItem.classList.add('in-use');
            }
        }
    }
    
    updateAgentsFromResponse(result) {
        // Reset all agents
        this.resetAgentStates();
        
        // Determine which agents were used based on the response
        const queryType = this.inferQueryType(result);
        
        if (queryType === 'sql') {
            this.setAgentState('sqlite', 'active');
            this.setAgentState('sql_validation', 'active');
            if (result.sql_query) {
                this.setAgentState('python_repl', 'active');
            }
        } else if (queryType === 'memory') {
            this.setAgentState('chroma', 'active');
        } else {
            this.setAgentState('general', 'active');
        }
    }
    
    inferQueryType(result) {
        // Infer the query type based on the response structure
        if (result.sql_query) {
            return 'sql';
        } else if (result.response && result.response.includes('previous interactions')) {
            return 'memory';
        } else {
            return 'general';
        }
    }
    
    showActiveAgents(agentNames) {
        // Reset all agents first
        this.resetAgentStates();
        
        // Set specified agents as in-use
        agentNames.forEach(agentName => {
            this.setAgentState(agentName, 'in-use');
        });
        
        // Keep the agents visible (no auto-reset)
        // User can see which agents were used for their last query
    }
    
    showAgentOverlay() {
        this.agentOverlay.classList.remove('hidden');
        this.agentToggle.classList.add('active');
    }
    
    hideAgentOverlay() {
        this.agentOverlay.classList.add('hidden');
        this.agentToggle.classList.remove('active');
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ChatApp();
});

// Add some keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K to focus input
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('messageInput').focus();
    }
});

// Add error handling for global errors
window.addEventListener('error', (e) => {
    console.error('Global error:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('Unhandled promise rejection:', e.reason);
});