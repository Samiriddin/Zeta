# -*- coding: utf-8 -*-
"""
Веб-интерфейс для Zeta — ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ.
Доступ: http://localhost:5000
"""

import os
import sys
import webbrowser
import threading
import time
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.ai_engine import ask_zeta_sync
from core.memory import get_history, get_facts, clear_history, delete_fact
from modules.system_monitor import get_system_status
from core.screen_capture import take_screenshot

# ========== СОЗДАЁМ ПРИЛОЖЕНИЕ ==========
app = Flask(__name__)
app.secret_key = "zeta_secret_key_2026"
# ВАЖНО: Чтобы русские буквы отображались нормально, а не как \u...
app.config['JSON_AS_ASCII'] = False
CORS(app)

# ========== HTML ==========
HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Zeta Web — ИИ-помощник</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #1e1e2e;
            --bg-chat: #181825;
            --bg-input: #313244;
            --text-primary: #cdd6f4;
            --text-secondary: #a6adc8;
            --text-muted: #6c7086;
            --accent: #89b4fa;
            --accent-hover: #74c7ec;
            --accent-text: #1e1e2e;
            --border: #313244;
            --danger: #f38ba8;
            --success: #a6e3a1;
            --radius-sm: 10px;
            --transition: 0.3s ease;
        }
        
        .light {
            --bg-primary: #f0f0f0;
            --bg-secondary: #ffffff;
            --bg-chat: #f5f5f5;
            --bg-input: #e8e8e8;
            --text-primary: #222222;
            --text-secondary: #555555;
            --text-muted: #999999;
            --border: #dddddd;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            transition: background var(--transition), color var(--transition);
        }
        
        .header {
            background: var(--bg-secondary);
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            transition: background var(--transition), border var(--transition);
        }
        .header-left { display: flex; align-items: center; gap: 12px; }
        .header-logo { font-size: 28px; }
        .header-title { font-size: 20px; font-weight: bold; color: var(--accent); }
        .header-title span { color: var(--text-primary); }
        .header-badge {
            font-size: 11px;
            background: var(--accent);
            color: var(--accent-text);
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: bold;
        }
        .header-right { display: flex; align-items: center; gap: 12px; }
        .header-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: var(--text-secondary);
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            animation: pulse 2s infinite;
        }
        .status-dot.online { background: var(--success); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        
        .theme-toggle {
            background: none;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 6px 12px;
            color: var(--text-primary);
            cursor: pointer;
            font-size: 16px;
            transition: var(--transition);
        }
        .theme-toggle:hover { background: var(--bg-input); }
        
        .menu-bar {
            background: var(--bg-secondary);
            padding: 8px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            flex-shrink: 0;
            transition: background var(--transition), border var(--transition);
        }
        .menu-bar button {
            background: transparent;
            color: var(--text-secondary);
            border: 1px solid transparent;
            border-radius: var(--radius-sm);
            padding: 6px 14px;
            font-size: 12px;
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
        }
        .menu-bar button:hover {
            background: var(--bg-input);
            color: var(--text-primary);
        }
        .menu-bar button.danger:hover {
            border-color: var(--danger);
            color: var(--danger);
        }
        
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: var(--bg-chat);
            transition: background var(--transition);
        }
        .message {
            max-width: 85%;
            padding: 10px 16px;
            border-radius: var(--radius-sm);
            word-wrap: break-word;
            animation: fadeIn 0.3s ease;
            transition: background var(--transition), color var(--transition);
        }
        .message.user {
            align-self: flex-end;
            background: var(--accent);
            color: var(--accent-text);
            border-bottom-right-radius: 4px;
        }
        .message.zeta {
            align-self: flex-start;
            background: var(--bg-input);
            color: var(--text-primary);
            border-bottom-left-radius: 4px;
        }
        .message.system {
            align-self: center;
            background: var(--bg-input);
            color: var(--text-secondary);
            font-size: 12px;
            padding: 6px 16px;
            border-radius: 20px;
            max-width: 90%;
        }
        .message .sender { font-size: 11px; font-weight: bold; margin-bottom: 4px; opacity: 0.7; }
        .message .text { font-size: 14px; line-height: 1.6; }
        .message .text pre {
            background: var(--bg-primary);
            padding: 10px;
            border-radius: var(--radius-sm);
            overflow-x: auto;
            font-size: 12px;
            margin: 6px 0;
            color: var(--text-primary);
        }
        .message .text img { max-width: 100%; border-radius: var(--radius-sm); margin-top: 4px; }
        
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        
        .typing-indicator {
            align-self: flex-start;
            background: var(--bg-input);
            padding: 10px 18px;
            border-radius: var(--radius-sm);
            border-bottom-left-radius: 4px;
            display: none;
            font-size: 13px;
            color: var(--text-secondary);
        }
        .typing-indicator .dots { display: inline-block; animation: dots 1.4s infinite; }
        @keyframes dots { 0%, 20% { content: ''; } 40% { content: '.'; } 60% { content: '..'; } 80% { content: '...'; } }
        
        .input-container {
            background: var(--bg-secondary);
            padding: 12px 20px;
            border-top: 1px solid var(--border);
            display: flex;
            gap: 10px;
            flex-shrink: 0;
            transition: background var(--transition), border var(--transition);
        }
        .input-container input {
            flex: 1;
            background: var(--bg-input);
            border: none;
            border-radius: var(--radius-sm);
            padding: 12px 18px;
            color: var(--text-primary);
            font-size: 14px;
            outline: none;
            transition: border var(--transition), background var(--transition);
        }
        .input-container input:focus { border: 2px solid var(--accent); }
        .input-container input::placeholder { color: var(--text-muted); }
        .input-container button {
            background: var(--accent);
            color: var(--accent-text);
            border: none;
            border-radius: var(--radius-sm);
            padding: 12px 24px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: background var(--transition);
            white-space: nowrap;
        }
        .input-container button:hover { background: var(--accent-hover); }
        .input-container button:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .chat-container::-webkit-scrollbar { width: 4px; }
        .chat-container::-webkit-scrollbar-track { background: var(--bg-chat); }
        .chat-container::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
        
        @media (max-width: 768px) {
            .header-title { font-size: 16px; }
            .header-badge { display: none; }
            .message { max-width: 92%; }
            .input-container input { font-size: 16px; padding: 10px 14px; }
            .input-container button { padding: 10px 16px; font-size: 13px; }
            .menu-bar button { font-size: 11px; padding: 4px 10px; }
            .chat-container { padding: 12px; }
            .header { padding: 10px 12px; }
            .menu-bar { padding: 6px 12px; gap: 4px; }
            .input-container { padding: 10px 12px; }
        }
        @media (max-width: 480px) {
            .header-title { font-size: 14px; }
            .header-logo { font-size: 22px; }
            .header-status { font-size: 10px; }
            .message .text { font-size: 13px; }
            .menu-bar button { font-size: 10px; padding: 3px 8px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <span class="header-logo">🤖</span>
            <span class="header-title">Zeta <span>Web</span></span>
            <span class="header-badge">v2.0</span>
        </div>
        <div class="header-right">
            <div class="header-status">
                <span class="status-dot online" id="statusDot"></span>
                <span id="statusText">Онлайн</span>
            </div>
            <button class="theme-toggle" onclick="toggleTheme()" title="Сменить тему">🌓</button>
        </div>
    </div>

    <div class="menu-bar">
        <button onclick="clearChat()">🗑️ Очистить</button>
        <button onclick="exportChat()">📤 Экспорт</button>
        <button onclick="getStatus()">📊 Статус</button>
        <button onclick="getFacts()">🧠 Факты</button>
        <button onclick="takeScreenshot()">🖥️ Скриншот</button>
        <button onclick="showHistory()">📜 История</button>
        <button class="danger" onclick="clearFacts()">🧹 Очистить факты</button>
    </div>

    <div class="chat-container" id="chatContainer">
        <div class="message system">🤖 Добро пожаловать в Zeta Web!</div>
        <div class="message system">💡 Напиши что-нибудь внизу или используй кнопки меню</div>
    </div>

    <div class="typing-indicator" id="typingIndicator">
        🤔 Zeta думает<span class="dots">...</span>
    </div>

    <div class="input-container">
        <input type="text" id="messageInput" placeholder="Напиши что-нибудь..." autofocus>
        <button onclick="sendMessage()" id="sendBtn">Отправить</button>
    </div>

    <script>
        console.log("✅ Zeta Web загружен!");

        let darkMode = localStorage.getItem('zeta_theme') !== 'light';
        let chatHistory = [];

        function applyTheme() {
            if (!darkMode) {
                document.body.classList.add('light');
            } else {
                document.body.classList.remove('light');
            }
            localStorage.setItem('zeta_theme', darkMode ? 'dark' : 'light');
        }
        applyTheme();

        function toggleTheme() {
            darkMode = !darkMode;
            applyTheme();
        }

        function addMessage(type, sender, text) {
            const container = document.getElementById('chatContainer');
            const div = document.createElement('div');
            div.className = 'message ' + type;
            const senderHTML = type !== 'system' ? '<div class="sender">' + sender + '</div>' : '';
            // ИСПРАВЛЕНО: Используем одиночный слеш для регулярного выражения в JS
            let textHTML = text.replace(/\\n/g, '<br>');
            textHTML = textHTML.replace(/```([\\s\\S]*?)```/g, '<pre><code>$1</code></pre>');
            div.innerHTML = senderHTML + '<div class="text">' + textHTML + '</div>';
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            addMessage('user', 'Вы', text);
            chatHistory.push({role: 'user', content: text});

            document.getElementById('typingIndicator').style.display = 'block';
            document.getElementById('sendBtn').disabled = true;

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                });
                const data = await response.json();
                document.getElementById('typingIndicator').style.display = 'none';
                document.getElementById('sendBtn').disabled = false;
                if (data.error) {
                    addMessage('system', 'Система', '⚠️ ' + data.error);
                } else {
                    addMessage('zeta', 'Zeta', data.response);
                    chatHistory.push({role: 'zeta', content: data.response});
                }
            } catch (error) {
                document.getElementById('typingIndicator').style.display = 'none';
                document.getElementById('sendBtn').disabled = false;
                addMessage('system', 'Система', '⚠️ Ошибка: ' + error);
            }
        }

        async function clearChat() {
            if (!confirm('Очистить чат?')) return;
            await fetch('/clear', { method: 'POST' });
            document.getElementById('chatContainer').innerHTML = '';
            chatHistory = [];
            addMessage('system', 'Система', '🗑️ Чат очищен');
        }

        function exportChat() {
            if (chatHistory.length === 0) {
                addMessage('system', 'Система', '📭 Нет сообщений');
                return;
            }
            // ИСПРАВЛЕНО: Убираем лишние экранированные слеши
            let text = '📜 Экспорт чата Zeta\\n' + '='.repeat(40) + '\\n\\n';
            for (let msg of chatHistory) {
                text += (msg.role === 'user' ? 'Вы' : 'Zeta') + ': ' + msg.content + '\\n\\n';
            }
            const blob = new Blob([text], {type: 'text/plain'});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'zeta_chat_' + new Date().toISOString().slice(0,10) + '.txt';
            a.click();
            addMessage('system', 'Система', '📤 Экспортирован');
        }

        async function getStatus() {
            addMessage('system', 'Система', '📊 Запрос статуса...');
            const res = await fetch('/status');
            const data = await res.json();
            if (data.error) {
                addMessage('system', 'Система', '⚠️ ' + data.error);
            } else {
                addMessage('zeta', 'Zeta', data.status);
            }
        }

        async function getFacts() {
            addMessage('system', 'Система', '🧠 Запрос фактов...');
            const res = await fetch('/facts');
            const data = await res.json();
            if (data.error) {
                addMessage('system', 'Система', '⚠️ ' + data.error);
            } else {
                addMessage('zeta', 'Zeta', data.facts);
            }
        }

        async function takeScreenshot() {
            addMessage('system', 'Система', '📸 Скриншот...');
            const res = await fetch('/screenshot');
            const data = await res.json();
            if (data.error) {
                addMessage('system', 'Система', '⚠️ ' + data.error);
            } else if (data.image) {
                const container = document.getElementById('chatContainer');
                const div = document.createElement('div');
                div.className = 'message zeta';
                div.innerHTML = '<div class="sender">Zeta</div><div class="text"><img src="data:image/jpeg;base64,' + data.image + '"></div>';
                container.appendChild(div);
                container.scrollTop = container.scrollHeight;
            }
        }

        async function showHistory() {
            const res = await fetch('/history');
            const data = await res.json();
            if (data.error) {
                addMessage('system', 'Система', '⚠️ ' + data.error);
            } else {
                addMessage('zeta', 'Zeta', data.history);
            }
        }

        async function clearFacts() {
            if (!confirm('🧹 Очистить все факты?')) return;
            const res = await fetch('/clear_facts', { method: 'POST' });
            const data = await res.json();
            addMessage('system', 'Система', data.message || '🧹 Факты очищены');
        }

        document.getElementById('messageInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
            }
        });

        document.addEventListener('click', function() {
            document.getElementById('messageInput').focus();
        });

        console.log("✅ Все функции загружены!");
    </script>
</body>
</html>
"""


# ========== МАРШРУТЫ ==========

@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Пустое сообщение'})
    try:
        response = ask_zeta_sync(user_message)
        return jsonify({'response': response})
    except Exception as e:
        # Исправление: возвращаем ошибку с русским текстом корректно
        return jsonify({'error': str(e)})


@app.route('/clear', methods=['POST'])
def clear():
    clear_history()
    return jsonify({'status': 'ok'})


@app.route('/history')
def history():
    try:
        history_list = get_history(limit=20)
        if not history_list:
            return jsonify({'history': '📭 История пуста.'})
        # ИСПРАВЛЕНО: заменяем \\n на \n
        text = "📜 **Последние сообщения:**\n\n"
        for msg in history_list[-10:]:
            role = "👤 Вы" if msg["role"] == "user" else "🤖 Z"
            content = msg["content"][:200] + ("..." if len(msg["content"]) > 200 else "")
            text += f"{role}: {content}\n"
        return jsonify({'history': text})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/status')
def status():
    try:
        status_text = get_system_status()
        return jsonify({'status': status_text})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/facts')
def facts():
    try:
        facts_list = get_facts()
        
        # ИСПРАВЛЕНО: Отфильтровываем технические настройки, которые не являются фактами
        settings_keys = {"notif_interval", "disk_threshold", "ram_threshold", "cpu_threshold", 
                         "smart_notifications", "max_tokens", "widget_opacity", "ai_temperature", 
                         "project_path", "context_tokens", "ai_model", "tts_speed", "tts_voice"}
        
        filtered_facts = [f for f in facts_list if f['key'] not in settings_keys]
        
        if not filtered_facts:
            return jsonify({'facts': '🧠 У меня пока нет фактов о вас.'})
            
        # ИСПРАВЛЕНО: заменяем \\n на \n
        text = "🧠 **Факты о вас:**\n\n"
        for fact in filtered_facts:
            text += f"• {fact['key']}: {fact['content']}\n"
        return jsonify({'facts': text})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/clear_facts', methods=['POST'])
def clear_facts():
    try:
        facts = get_facts()
        for fact in facts:
            delete_fact(fact['key'])
        return jsonify({'message': '🧹 Все факты очищены!'})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/screenshot')
def screenshot():
    try:
        img_base64 = take_screenshot()
        if not img_base64:
            return jsonify({'error': 'Не удалось сделать скриншот'})
        return jsonify({'image': img_base64})
    except Exception as e:
        return jsonify({'error': str(e)})


# ========== ЗАПУСК ==========
def run_server(port=5000):
    print(f"""
╔══════════════════════════════════════════════════════════╗
║                    🌐 Zeta Web v2.0                     ║
╠══════════════════════════════════════════════════════════╣
║  📱 Открой в браузере: http://localhost:{port}        ║
║  📱 С телефона: http://[IP-адрес]:{port}              ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Функция для плавного открытия браузера
    def open_browser():
        time.sleep(2)
        webbrowser.open(f'http://localhost:{port}')

    # Открываем браузер в отдельном потоке, чтобы не блокировать Flask
    threading.Thread(target=open_browser, daemon=True).start()

    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    run_server()