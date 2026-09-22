/* ============================================================
   Zeta PWA — логика
   Навигация, чат, демо-ответы, настройки, тема
   ============================================================ */

// ========== ДЕМО-ОТВЕТЫ ==========

const DEMO_RESPONSES = [
    {
        keys: ["привет", "здравствуй", "хай", "hello", "hi", "салам", "salom"],
        answers: [
            "Привет! Я Zeta 😊 Чем могу помочь?",
            "Здравствуй! Готова к работе.",
            "Привет-привет! Что нужно?",
        ]
    },
    {
        keys: ["как дела", "как ты", "как жизнь", "что делаешь"],
        answers: [
            "Отлично! Работаю на полную. А у тебя как?",
            "Всё хорошо! Готова помочь.",
            "Прекрасно — как всегда 😎",
        ]
    },
    {
        keys: ["что умеешь", "функции", "возможности", "help", "помощь"],
        answers: [
            "🧠 **Я умею:**\n\n" +
            "• 💬 Общаться и отвечать на вопросы\n" +
            "• 👁️ Анализировать фото и скриншоты\n" +
            "• 🎤 Говорить и слушать\n" +
            "• 💻 Открывать приложения\n" +
            "• 🌐 Работать с браузером\n" +
            "• 📅 Планировать задачи\n" +
            "• 🤖 Автоматизировать действия\n" +
            "• 📄 Читать документы\n\n" +
            "⚠️ Сейчас это демо. В полной версии — всё работает на ПК!"
        ]
    },
    {
        keys: ["кто ты", "что ты", "твоё имя", "как тебя зовут"],
        answers: [
            "Я — **Zeta** 🤖 Локальный ИИ-ассистент.\n" +
            "Меня создал **Самир** из Узбекистана 🇺🇿\n" +
            "Работаю на твоём ПК, без облака и подписок."
        ]
    },
    {
        keys: ["кто создал", "создатель", "автор", "кто тебя сделал"],
        answers: [
            "Меня создал **Самриддин (Самир)** — 17-летний разработчик из Хорезма, Узбекистан 🇺🇿\n\n" +
            "Он пишет меня на **Python + PyQt6 + Ollama**.\n" +
            "Проект открытый: https://github.com/Samiriddin/Zeta"
        ]
    },
    {
        keys: ["спасибо", "благодарю", "thanks", "raxmat", "рахмат"],
        answers: [
            "Всегда рада помочь! 😊",
            "Обращайся!",
            "Пожалуйста! 🌟",
        ]
    },
    {
        keys: ["пока", "до свидания", "бай", "bye"],
        answers: [
            "До встречи! 👋",
            "Пока-пока!",
            "До скорого!",
        ]
    },
    {
        keys: ["узбекистан", "uzbekistan", "родина", "хорезм", "хоразм"],
        answers: [
            "🇺🇿 Узбекистан — моя родина!\n" +
            "Я — первый узбекский локальный ИИ-ассистент.\n" +
            "В будущем — ещё и робот Z! 🤖"
        ]
    },
    {
        keys: ["github", "гитхаб", "репозиторий", "код"],
        answers: [
            "📦 Мой код открыт:\n" +
            "https://github.com/Samiriddin/Zeta\n\n" +
            "Там 22 000+ строк кода, 25+ модулей.\n" +
            "Поставь ⭐ если нравится!"
        ]
    },
    {
        keys: ["время", "который час", "сколько времени"],
        answers: [
            () => `Сейчас ${new Date().toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})} ⏰`
        ]
    },
    {
        keys: ["дата", "какое число", "сегодня"],
        answers: [
            () => `Сегодня ${new Date().toLocaleDateString('ru-RU', {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'})} 📅`
        ]
    },
];

const FALLBACK_RESPONSES = [
    "⚠️ Это **демо-версия** Zeta.\n\n" +
    "Настоящая Zeta работает на твоём ПК с моделью **zeta-universal** (llama3.1:8b).\n\n" +
    "📱 Скачай полную версию:\n" +
    "https://github.com/Samiriddin/Zeta",

    "🤖 Я пока в демо-режиме. В полной версии я:\n" +
    "• Отвечаю на любые вопросы\n" +
    "• Вижу фото и экран\n" +
    "• Говорю голосом\n" +
    "• Управляю ПК\n\n" +
    "GitHub: https://github.com/Samiriddin/Zeta",

    "💡 Это макет приложения. Настоящая Zeta — на ПК.\n" +
    "Скачать: https://github.com/Samiriddin/Zeta",
];


// ========== ЭЛЕМЕНТЫ ==========

const chat = document.getElementById('chat');
const input = document.getElementById('input');
const btnSend = document.getElementById('btn-send');
const btnMic = document.getElementById('btn-mic');
const btnTheme = document.getElementById('btn-theme');
const typing = document.getElementById('typing');
const screens = document.querySelectorAll('.screen');
const navBtns = document.querySelectorAll('.nav-btn');

const themeSelect = document.getElementById('theme-select');
const langSelect = document.getElementById('lang-select');
const fontSize = document.getElementById('font-size');
const fontSizeValue = document.getElementById('font-size-value');


// ========== НАСТРОЙКИ ==========

const settings = {
    theme: localStorage.getItem('zeta_theme') || 'dark',
    lang: localStorage.getItem('zeta_lang') || 'ru',
    fontSize: parseInt(localStorage.getItem('zeta_font_size')) || 15,
};

function applyTheme() {
    document.documentElement.setAttribute('data-theme', settings.theme);
    document.querySelector('meta[name="theme-color"]')
        .setAttribute('content', settings.theme === 'dark' ? '#030817' : '#f5f7ff');
    if (themeSelect) themeSelect.value = settings.theme;
}

function applyFontSize() {
    document.body.style.fontSize = settings.fontSize + 'px';
    if (fontSizeValue) fontSizeValue.textContent = settings.fontSize + 'px';
}

function saveSettings() {
    localStorage.setItem('zeta_theme', settings.theme);
    localStorage.setItem('zeta_lang', settings.lang);
    localStorage.setItem('zeta_font_size', settings.fontSize);
}


// ========== НАВИГАЦИЯ ==========

function showScreen(name) {
    screens.forEach(s => {
        if (s.id === 'screen-' + name) {
            s.hidden = false;
        } else {
            s.hidden = true;
        }
    });

    navBtns.forEach(b => {
        b.classList.toggle('active', b.dataset.screen === name);
    });
}

navBtns.forEach(btn => {
    btn.addEventListener('click', () => showScreen(btn.dataset.screen));
});

document.querySelectorAll('[data-back]').forEach(btn => {
    btn.addEventListener('click', () => showScreen('chat'));
});


// ========== ЧАТ ==========

function addMessage(sender, text) {
    const msg = document.createElement('div');
    msg.className = 'msg ' + (sender === 'user' ? 'user' : 'zeta');

    const senderName = sender === 'user' ? 'Вы' : 'Zeta';
    const senderEl = document.createElement('div');
    senderEl.className = 'sender';
    senderEl.textContent = senderName;

    const textEl = document.createElement('div');
    textEl.innerHTML = formatText(text);

    msg.appendChild(senderEl);
    msg.appendChild(textEl);
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
}

function formatText(text) {
    // Экранируем HTML
    text = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Жирный **text**
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Ссылки
    text = text.replace(/(https?:\/\/[^\s]+)/g,
        '<a href="$1" target="_blank" style="color: var(--blue2);">$1</a>');

    // Переносы строк
    text = text.replace(/\n/g, '<br>');

    return text;
}

function findResponse(text) {
    const lower = text.toLowerCase().trim();

    // Ищем ключи
    for (const resp of DEMO_RESPONSES) {
        for (const key of resp.keys) {
            if (lower.includes(key)) {
                const answer = resp.answers[Math.floor(Math.random() * resp.answers.length)];
                return typeof answer === 'function' ? answer() : answer;
            }
        }
    }

    // Fallback
    return FALLBACK_RESPONSES[Math.floor(Math.random() * FALLBACK_RESPONSES.length)];
}

function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    addMessage('user', text);

    // Показываем "печатает"
    typing.hidden = false;
    btnSend.disabled = true;
    chat.scrollTop = chat.scrollHeight;

    // Имитация задержки
    const delay = 400 + Math.random() * 800;

    setTimeout(() => {
        typing.hidden = true;
        btnSend.disabled = false;

        const response = findResponse(text);
        addMessage('zeta', response);
    }, delay);
}

btnSend.addEventListener('click', sendMessage);

input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
    }
});


// ========== КНОПКА МИКРОФОНА (заглушка) ==========

btnMic.addEventListener('click', () => {
    addMessage('zeta',
        "🎤 В **демо-версии** голосовой ввод недоступен.\n\n" +
        "В полной версии Zeta я умею:\n" +
        "• Слушать голос (STT)\n" +
        "• Отвечать голосом (TTS, 6 голосов)\n" +
        "• Активироваться по «Hey Jarvis»\n\n" +
        "📱 Скачать: https://github.com/Samiriddin/Zeta"
    );
});


// ========== КНОПКА ТЕМЫ ==========

btnTheme.addEventListener('click', () => {
    settings.theme = settings.theme === 'dark' ? 'light' : 'dark';
    applyTheme();
    saveSettings();
});


// ========== НАСТРОЙКИ UI ==========

if (themeSelect) {
    themeSelect.addEventListener('change', (e) => {
        settings.theme = e.target.value;
        applyTheme();
        saveSettings();
    });
}

if (langSelect) {
    langSelect.addEventListener('change', (e) => {
        settings.lang = e.target.value;
        saveSettings();
        addMessage('zeta', `🌍 Язык изменён на **${e.target.options[e.target.selectedIndex].text}**\n\n⚠️ В демо — только интерфейс. Полный перевод — в релизе.`);
    });
}

if (fontSize) {
    fontSize.addEventListener('input', (e) => {
        settings.fontSize = parseInt(e.target.value);
        applyFontSize();
        saveSettings();
    });
}


// ========== ПРИВЕТСТВИЕ ==========

function greet() {
    addMessage('zeta',
        "👋 Привет! Я **Zeta** — локальный ИИ-ассистент.\n\n" +
        "🇺🇿 Создан в Узбекистане.\n\n" +
        "💡 **Что можно попробовать:**\n" +
        "• «привет»\n" +
        "• «что умеешь»\n" +
        "• «кто тебя создал»\n" +
        "• «сколько времени»\n\n" +
        "⚠️ Это **демо-версия** с заранее заготовленными ответами.\n" +
        "В полной версии — настоящий ИИ на твоём ПК! 🚀"
    );
}


// ========== ЗАПУСК ==========

applyTheme();
applyFontSize();
greet();

// Фокус на инпут при загрузке
setTimeout(() => input.focus(), 100);

console.log('✅ Zeta PWA запущена (демо-режим)');