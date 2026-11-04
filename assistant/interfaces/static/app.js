// --- CONFIGURACIÓN PARA HOSTING ---
// Si estás en local, deja "". Si estás en Render, pon la URL: "https://tu-app.onrender.com"
const API_BASE = ""; 

const MASTER_KEY = "mango-secreto-123"; 
const fetchHeaders = {
    "Content-Type": "application/json",
    "X-Master-Key": MASTER_KEY
};

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
const micBtn = document.getElementById('mic-btn');
const ttsToggle = document.getElementById('tts-toggle');

let isListening = false;
let ttsEnabled = false;
let recognition = null;

if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = 'es-ES';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
        isListening = true;
        micBtn.style.color = '#f87171';
        micBtn.style.background = 'rgba(248, 113, 113, 0.2)';
    };
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        chatInput.value = transcript;
        setTimeout(() => chatForm.requestSubmit(), 300);
    };
    recognition.onerror = (event) => { resetMicBtn(); };
    recognition.onend = () => { resetMicBtn(); };
} else {
    micBtn.style.display = 'none';
}

function resetMicBtn() {
    isListening = false;
    micBtn.style.color = '';
    micBtn.style.background = '';
}

micBtn.addEventListener('click', () => {
    if (!recognition) return;
    if (isListening) recognition.stop();
    else { try { recognition.start(); } catch (e) { console.error(e); } }
});

ttsToggle.addEventListener('click', () => {
    ttsEnabled = !ttsEnabled;
    if (ttsEnabled) {
        ttsToggle.style.color = '#34d399';
        ttsToggle.style.background = 'rgba(52, 211, 153, 0.2)';
    } else {
        ttsToggle.style.color = '';
        ttsToggle.style.background = '';
        window.speechSynthesis.cancel();
    }
});

function speakText(text) {
    if (!ttsEnabled) return;
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/[*#_`~]/g, '').replace(/\[.*?\]\(.*?\)/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'es-ES';
    utterance.rate = 1.0;
    window.speechSynthesis.speak(utterance);
}

themeToggle.addEventListener('click', () => {
    document.body.classList.toggle('light-theme');
    if (document.body.classList.contains('light-theme')) {
        hljsTheme.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
    } else {
        hljsTheme.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css';
    }
});

uploadBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
    if (!fileInput.files.length) return;
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);
    addMessage('user', `Subiendo archivo: ${file.name}...`);
    try {
        const res = await fetch(API_BASE + '/upload', { 
            method: 'POST', 
            body: formData,
            headers: { 'X-Master-Key': MASTER_KEY }
        });
        const data = await res.json();
        if (res.ok) addMessage('assistant', `He guardado el archivo **${data.filename}**. ¿Qué hacemos con él?`, true);
        else addMessage('assistant', 'Error al subir el archivo.');
    } catch (e) {
        addMessage('assistant', 'Error de conexión al subir.');
    }
    fileInput.value = '';
});

async function loadHistory() {
    try {
        const res = await fetch(API_BASE + '/history', { headers: fetchHeaders });
        const data = await res.json();
        chatContainer.innerHTML = '';
        if (data.messages.length === 0) {
            addMessage('assistant', '¡Hola! Soy Mango. ¿En qué puedo ayudarte hoy?', true);
            return;
        }
        data.messages.forEach(msg => {
            if (msg.content.startsWith('[TOOL')) return;
            addMessage(msg.role, msg.content, (msg.role === 'assistant'));
        });
    } catch (e) { console.error(e); }
}

chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + 'px';
});

chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.requestSubmit();
    }
});

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
        const response = await fetch(API_BASE + '/chat/stream', {
            method: 'POST',
            headers: fetchHeaders,
            body: JSON.stringify({ message: message, model: modelSelector.value })
        });

        if (!response.ok) throw new Error(`Error: ${response.status}`);

        removeTypingIndicator(typingId);
        
        const msgDiv = document.createElement('div');
        msgDiv.className = 'msg assistant';
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'msg-avatar';
        avatarDiv.textContent = 'AI';
        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content';
        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(contentDiv);
        chatContainer.appendChild(msgDiv);
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let fullText = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            fullText += chunk;
            contentDiv.innerHTML = marked.parse(fullText);
            scrollToBottom();
        }

        speakText(fullText);
        setStatus('connected');

    } catch (error) {
        removeTypingIndicator(typingId);
        addMessage('assistant', `⚠️ Error de conexión.`);
        setStatus('error');
    }
});

newChatBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    try {
        await fetch(API_BASE + '/clear', { method: 'POST', headers: fetchHeaders });
        chatContainer.innerHTML = '';
        addMessage('assistant', '¡Historial borrado! ¿De qué hablamos?', true);
    } catch (e) {
        chatContainer.innerHTML = '';
        addMessage('assistant', '¡Interfaz reiniciada!', true);
    }
});

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
                    setTimeout(() => { copyBtn.innerHTML = 'Copiar'; copyBtn.classList.remove('copied'); }, 2000);
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

loadHistory();