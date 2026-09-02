# core/claude_client.py — Подключение к Claude API

import anthropic
from config import CLAUDE_API_KEY, ZETA_PERSONALITY
from core.memory import save_message, get_history

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def ask_claude(user_message: str) -> str:
    """Отправляет сообщение Клоду и возвращает ответ"""
    try:
        # Сохраняем сообщение пользователя
        save_message("user", user_message)

        # Берём историю разговора
        history = get_history(limit=20)

        # Отправляем запрос
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=ZETA_PERSONALITY,
            messages=history
        )

        # Получаем ответ
        answer = response.content[0].text

        # Сохраняем ответ Зеты
        save_message("assistant", answer)

        return answer

    except anthropic.AuthenticationError:
        return "⚠️ Неверный API ключ. Проверь config.py"
    except anthropic.APIConnectionError:
        return "⚠️ Нет соединения с интернетом. Переключаюсь на офлайн режим..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"