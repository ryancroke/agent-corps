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
        
        this.initializeEventListeners();
        this.checkServerHealth();
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
            this.addMessage('assistant', result.response, result.sql_query);
            
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessage('assistant', `Sorry, I encountered an error: ${error.message}`, null, true);
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