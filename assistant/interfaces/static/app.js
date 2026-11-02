// Configurar marked
if (typeof marked !== 'undefined') {
    marked.setOptions({
        breaks: true,
        highlight: function (code, lang) {
            const language = hljs.getLanguage(lang) ? lang : 'plaintext';
            return hljs.highlight(code, { language }).value;
        }
    });
}

const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatContainer = document.getElementById('chat-container');
const sendBtn = document.getElementById('send-btn');
const statusIndicator = document.getElementById('status-indicator');
const newChatBtn = document.getElementById('new-chat-btn');
const modelSelector = document.getElementById('model-selector');
const themeToggle = document.getElementById('theme-toggle');
const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-input');
const hljsTheme = document.getElementById('hljs-theme');

// --- Lógica del Tema ---
themeToggle.addEventListener('click', () => {
    document.body.classList.toggle('light-theme');
    if (document.body.classList.contains('light-theme')) {
        hljsTheme.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
    } else {
        hljsTheme.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css';
    }
});

// --- Lógica de Subir Archivo ---
uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async () => {
    if (!fileInput.files.length) return;
    const file = fileInput.files[0];
    
    const formData = new FormData();
    formData.append('file', file);
    
    addMessage('user', `Subiendo archivo: ${file.name}...`);
    
    try {
        const res = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if (res.ok) {
            addMessage('assistant', `He guardado el archivo **${data.filename}** en el workspace. ¿Qué quieres que haga con él?`, true);
        } else {
            addMessage('assistant', 'Error al subir el archivo.');
        }
    } catch (e) {
        addMessage('assistant', 'Error de conexión al subir el archivo.');
    }
    fileInput.value = ''; // Limpiar
});

// --- 1. Cargar historial al iniciar ---
async function loadHistory() {
    try {
        const res = await fetch('/history');
        const data = await res.json();
        chatContainer.innerHTML = '';
        if (data.messages.length === 0) {
            addMessage('assistant', '¡Hola! Soy tu asistente. ¿En qué puedo ayudarte hoy?', true);
            return;
        }
        data.messages.forEach(msg => {
            if (msg.content.startsWith('[TOOL')) return;
            addMessage(msg.role, msg.content, (msg.role === 'assistant'));
        });
    } catch (e) {
        console.error("No se pudo cargar el historial", e);
    }
}

// --- 2. Autoajustar el textarea ---
chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + 'px';
});

// --- 3. Manejar Enter ---
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.requestSubmit();
    }
});

// --- 4. Enviar mensaje ---
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    const typingId = showTypingIndicator();
    setStatus('thinking');

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, model: modelSelector.value })
        });

        if (!response.ok) throw new Error(`Error: ${response.status}`);

        const data = await response.json();
        removeTypingIndicator(typingId);
        addMessage('assistant', data.reply, true);
        setStatus('connected');

    } catch (error) {
        removeTypingIndicator(typingId);
        addMessage('assistant', `⚠️ Error de conexión.`);
        setStatus('error');
    }
});

// --- 5. Botón de Nueva Conversación ---
newChatBtn.addEventListener('click', async () => {
    if (!confirm('¿Borrar todo el historial y empezar de cero?')) return;
    try {
        await fetch('/clear', { method: 'POST' });
        chatContainer.innerHTML = '';
        addMessage('assistant', '¡Historial borrado! ¿De qué quieres hablar ahora?', true);
    } catch (e) {
        console.error(e);
    }
});

// --- 6. Función para añadir mensajes ---
function addMessage(role, text, isMarkdown = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `msg ${role}`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'msg-avatar';
    avatarDiv.textContent = role === 'user' ? 'Tú' : 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    
    if (isMarkdown && typeof marked !== 'undefined') {
        contentDiv.innerHTML = marked.parse(text);
        const preBlocks = contentDiv.querySelectorAll('pre');
        preBlocks.forEach(pre => {
            const code = pre.querySelector('code');
            if (!code) return;
            const copyBtn = document.createElement('button');
            copyBtn.className = 'copy-code-btn';
            copyBtn.innerHTML = 'Copiar';
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(code.innerText).then(() => {
                    copyBtn.innerHTML = '¡Copiado!';
                    copyBtn.classList.add('copied');
                    setTimeout(() => {
                        copyBtn.innerHTML = 'Copiar';
                        copyBtn.classList.remove('copied');
                    }, 2000);
                });
            });
            pre.style.position = 'relative';
            pre.appendChild(copyBtn);
        });
    } else {
        contentDiv.textContent = text;
    }

    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(contentDiv);
    chatContainer.appendChild(msgDiv);
    scrollToBottom();
}

// --- Auxiliares ---
function showTypingIndicator() {
    const id = 'typing-' + Date.now();
    const msgDiv = document.createElement('div');
    msgDiv.className = 'msg assistant';
    msgDiv.id = id;
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'msg-avatar';
    avatarDiv.textContent = 'AI';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content typing';
    contentDiv.innerHTML = '<span></span><span></span><span></span>';
    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(contentDiv);
    chatContainer.appendChild(msgDiv);
    scrollToBottom();
    return id;
}

function removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function setStatus(state) {
    if (!statusIndicator) return;
    statusIndicator.classList.remove('thinking', 'error', 'busy');
    if (state === 'thinking') {
        statusIndicator.innerHTML = '<span class="dot"></span> Pensando...';
        statusIndicator.classList.add('thinking');
    } else if (state === 'error') {
        statusIndicator.innerHTML = '<span class="dot"></span> Desconectado';
        statusIndicator.classList.add('error');
    } else {
        statusIndicator.innerHTML = '<span class="dot"></span> Conectado';
    }
}

// Arrancar
loadHistory();