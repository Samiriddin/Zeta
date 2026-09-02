# -*- coding: utf-8 -*-
"""
RAG (Retrieval-Augmented Generation) для Zeta.
Читает документы: PDF, Word, Excel, TXT.
Отвечает на вопросы по содержимому.
Поддерживает: семантический поиск (ChromaDB), поиск по ключевым словам (SQLite fallback).
"""

import os
import re
import hashlib
import sqlite3
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

# ========== КОНСТАНТЫ ==========

DB_PATH = "data/rag.db"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MAX_CONTENT_LENGTH = 10000
MAX_SEARCH_RESULTS = 5

# Проверка ChromaDB
try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

# ========== ОБРАБОТЧИКИ ДОКУМЕНТОВ ==========

def read_txt(file_path: str) -> str:
    """Читает текстовый файл с автоматическим определением кодировки."""
    encodings = ['utf-8', 'utf-16', 'windows-1251', 'cp866', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    
    # Если все кодировки не подошли — пробуем через chardet
    try:
        import chardet
        with open(file_path, 'rb') as f:
            raw = f.read()
            result = chardet.detect(raw)
            encoding = result.get('encoding', 'utf-8')
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
    except ImportError:
        return "⚠️ Установите chardet: pip install chardet"
    except Exception as e:
        return f"⚠️ Не удалось прочитать файл: {e}"


def read_pdf(file_path: str) -> str:
    """Читает PDF-файл с обработкой ошибок."""
    # Проверка размера
    if os.path.getsize(file_path) < 100:
        return "⚠️ Файл слишком маленький (возможно повреждён)"
    
    # Пробуем PyMuPDF
    try:
        import fitz
        text = ""
        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text()
            if page_text.strip():
                text += f"\n--- Страница {page_num} ---\n"
                text += page_text
        doc.close()
        if not text.strip():
            return "⚠️ Не удалось извлечь текст из PDF (возможно, это сканированный документ)"
        return text
    except ImportError:
        pass
    except Exception as e:
        return f"⚠️ Ошибка чтения PDF (PyMuPDF): {e}"
    
    # Fallback на PyPDF2
    try:
        import PyPDF2
        text = ""
        with open(file_path, 'rb') as f:
            try:
                reader = PyPDF2.PdfReader(f)
                if len(reader.pages) == 0:
                    return "⚠️ PDF не содержит страниц"
                for page_num, page in enumerate(reader.pages, 1):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += f"\n--- Страница {page_num} ---\n"
                            text += page_text
                    except Exception as e:
                        text += f"\n⚠️ Ошибка на странице {page_num}: {e}\n"
                if not text.strip():
                    return "⚠️ Не удалось извлечь текст из PDF (возможно, сканированный документ)"
                return text
            except PyPDF2.errors.PdfReadError as e:
                return f"⚠️ Ошибка чтения PDF: {e}"
    except ImportError:
        return "⚠️ Установите PyMuPDF (рекомендуется) или PyPDF2: pip install PyMuPDF"
    except Exception as e:
        return f"⚠️ Ошибка чтения PDF: {e}"


def read_docx(file_path: str) -> str:
    """Читает Word-файл (.docx)."""
    try:
        import docx
        doc = docx.Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        # Добавляем текст из таблиц
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join([cell.text for cell in row.cells])
                if row_text.strip():
                    text += "\n" + row_text
        return text if text.strip() else "⚠️ Документ пуст"
    except ImportError:
        return "⚠️ Установите python-docx: pip install python-docx"
    except Exception as e:
        return f"⚠️ Ошибка чтения DOCX: {e}"


def read_excel(file_path: str) -> str:
    """Читает Excel-файл (.xlsx)."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        text = ""
        for sheet in wb.worksheets:
            text += f"\n📋 Лист: {sheet.title}\n"
            for row in sheet.iter_rows(values=True):
                row_text = " | ".join([str(cell) if cell is not None else "" for cell in row])
                if row_text.strip():
                    text += row_text + "\n"
        return text if text.strip() else "⚠️ Excel файл пуст"
    except ImportError:
        return "⚠️ Установите openpyxl: pip install openpyxl"
    except Exception as e:
        return f"⚠️ Ошибка чтения Excel: {e}"


def read_csv(file_path: str) -> str:
    """Читает CSV-файл."""
    try:
        import csv
        text = ""
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                text += " | ".join(row) + "\n"
        return text if text.strip() else "⚠️ CSV файл пуст"
    except Exception as e:
        return f"⚠️ Ошибка чтения CSV: {e}"


def read_file(file_path: str) -> str:
    """Автоматически определяет тип файла и читает его."""
    if not os.path.exists(file_path):
        return f"⚠️ Файл не найден: {file_path}"
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt':
        return read_txt(file_path)
    elif ext == '.pdf':
        return read_pdf(file_path)
    elif ext == '.docx':
        return read_docx(file_path)
    elif ext in ['.xlsx', '.xls']:
        return read_excel(file_path)
    elif ext == '.csv':
        return read_csv(file_path)
    else:
        return f"⚠️ Неподдерживаемый формат: {ext}"


# ========== БАЗА ДАННЫХ (SQLite) ==========

def init_rag_db():
    """Создаёт таблицы для RAG."""
    os.makedirs("data", exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                path TEXT,
                content TEXT,
                hash TEXT,
                size INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER,
                chunk_text TEXT,
                chunk_index INTEGER,
                FOREIGN KEY (doc_id) REFERENCES documents (id)
            )
        ''')
        # Индексы для быстрого поиска
        conn.execute('CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_documents_name ON documents(name)')


def get_file_hash(file_path: str) -> str:
    """Вычисляет хеш файла для проверки изменений."""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return ""


def save_document(file_path: str, content: str) -> bool:
    """Сохраняет документ в базу данных."""
    if not content or len(content) < 10:
        return False
    
    file_hash = get_file_hash(file_path)
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    with sqlite3.connect(DB_PATH) as conn:
        # Проверяем, есть ли уже такой документ
        existing = conn.execute(
            "SELECT id, hash FROM documents WHERE path = ?", (file_path,)
        ).fetchone()
        
        if existing:
            doc_id, old_hash = existing
            if old_hash == file_hash:
                return True  # Файл не изменился
            # Обновляем
            conn.execute('''
                UPDATE documents SET content = ?, hash = ?, size = ?, updated_at = ?
                WHERE id = ?
            ''', (content, file_hash, file_size, datetime.now().isoformat(), doc_id))
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        else:
            # Добавляем новый
            conn.execute('''
                INSERT INTO documents (name, path, content, hash, size, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (file_name, file_path, content, file_hash, file_size,
                  datetime.now().isoformat(), datetime.now().isoformat()))
            doc_id = conn.lastrowid
        
        # Разбиваем на чанки
        chunks = split_text(content)
        for i, chunk in enumerate(chunks):
            conn.execute('''
                INSERT INTO chunks (doc_id, chunk_text, chunk_index)
                VALUES (?, ?, ?)
            ''', (doc_id, chunk, i))
    
    return True


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Разбивает текст на чанки."""
    if not text:
        return []
    
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks


# ========== СЕМАНТИЧЕСКИЙ ПОИСК (ChromaDB) ==========

def init_chroma():
    """Инициализирует ChromaDB."""
    if not HAS_CHROMA:
        return None
    
    try:
        client = chromadb.PersistentClient(path="data/rag_vectors")
        collection = client.get_or_create_collection(
            name="documents",
            embedding_function=embedding_functions.DefaultEmbeddingFunction()
        )
        return collection
    except Exception as e:
        print(f"⚠️ Ошибка инициализации ChromaDB: {e}")
        return None


_collection = init_chroma()


def save_to_chroma(doc_id: int, chunks: List[str]):
    """Сохраняет чанки в ChromaDB."""
    if not _collection:
        return
    
    try:
        ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
        _collection.add(
            ids=ids,
            documents=chunks,
            metadatas=[{"doc_id": doc_id} for _ in chunks]
        )
    except Exception as e:
        print(f"⚠️ Ошибка сохранения в ChromaDB: {e}")


def search_chroma(query: str, limit: int = MAX_SEARCH_RESULTS) -> List[Dict]:
    """Семантический поиск в ChromaDB."""
    if not _collection:
        return []
    
    try:
        results = _collection.query(
            query_texts=[query],
            n_results=limit
        )
        
        if not results['documents'] or not results['documents'][0]:
            return []
        
        docs = []
        for i, doc_text in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i] if results['metadatas'] else {}
            docs.append({
                'content': doc_text,
                'doc_id': metadata.get('doc_id', 0),
                'score': 1.0 - results['distances'][0][i] if results['distances'] else 0,
                'preview': doc_text[:300]
            })
        return docs
    except Exception as e:
        print(f"⚠️ Ошибка поиска в ChromaDB: {e}")
        return []


# ========== ПОИСК ПО КЛЮЧЕВЫМ СЛОВАМ (SQLite fallback) ==========

def search_documents(query: str, limit: int = MAX_SEARCH_RESULTS) -> List[Dict]:
    """Ищет в документах по ключевым словам."""
    if not query or not query.strip():
        return []
    
    keywords = [k for k in query.lower().split() if len(k) > 2]
    if not keywords:
        return []
    
    with sqlite3.connect(DB_PATH) as conn:
        docs = conn.execute("SELECT id, name, content FROM documents").fetchall()
    
    results = []
    for doc_id, doc_name, content in docs:
        score = 0
        matched_keywords = []
        for keyword in keywords:
            count = content.lower().count(keyword)
            if count > 0:
                score += count
                matched_keywords.append(keyword)
        
        if score > 0:
            # Находим контекст вокруг совпадений
            preview = _get_relevant_preview(content, keywords, 300)
            results.append({
                'doc_id': doc_id,
                'name': doc_name,
                'score': score,
                'matched_keywords': matched_keywords,
                'preview': preview,
                'content': content[:MAX_CONTENT_LENGTH]
            })
    
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:limit]


def _get_relevant_preview(text: str, keywords: List[str], max_len: int = 300) -> str:
    """Возвращает релевантный фрагмент текста."""
    if not text:
        return ""
    
    text_lower = text.lower()
    # Находим первое совпадение
    for keyword in keywords:
        pos = text_lower.find(keyword)
        if pos != -1:
            start = max(0, pos - 50)
            end = min(len(text), pos + len(keyword) + 50)
            preview = text[start:end]
            if start > 0:
                preview = "..." + preview
            if end < len(text):
                preview = preview + "..."
            if len(preview) > max_len:
                preview = preview[:max_len] + "..."
            return preview
    
    return text[:max_len] + "..." if len(text) > max_len else text


# ========== УМНЫЙ ПОИСК (ГИБРИДНЫЙ) ==========

def hybrid_search(query: str, limit: int = MAX_SEARCH_RESULTS) -> List[Dict]:
    """Комбинирует векторный и ключевой поиск."""
    results = []
    
    # Векторный поиск (ChromaDB)
    if HAS_CHROMA:
        vector_results = search_chroma(query, limit)
        for r in vector_results:
            results.append({
                'doc_id': r.get('doc_id', 0),
                'name': f"Chunk {r.get('doc_id', 0)}",
                'score': r.get('score', 0),
                'matched_keywords': [],
                'preview': r.get('preview', ''),
                'content': r.get('content', ''),
                'source': 'vector'
            })
    
    # Ключевой поиск (SQLite)
    keyword_results = search_documents(query, limit)
    for r in keyword_results:
        results.append({
            'doc_id': r['doc_id'],
            'name': r['name'],
            'score': r['score'],
            'matched_keywords': r['matched_keywords'],
            'preview': r['preview'],
            'content': r['content'],
            'source': 'keyword'
        })
    
    # Сортировка и дедупликация
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # Убираем дубликаты по doc_id
    seen = set()
    unique_results = []
    for r in results:
        if r['doc_id'] not in seen:
            unique_results.append(r)
            seen.add(r['doc_id'])
    
    return unique_results[:limit]


# ========== RAG-ОТВЕТЫ ==========

def ask_with_rag(query: str) -> str:
    """Отвечает на вопрос, используя документы в базе."""
    if not query or not query.strip():
        return "⚠️ Укажите вопрос для поиска."

    results = hybrid_search(query, limit=MAX_SEARCH_RESULTS)
    
    if not results:
        return "📭 В базе нет подходящих документов. Загрузите файлы с помощью `загрузи документ путь_к_файлу`."
    
    # Формируем контекст
    context = "📄 **Найденные Dokumente:**\n\n"
    for i, res in enumerate(results, 1):
        if res.get('source') == 'vector':
            context += f"**{i}. [Векторный поиск]**\n"
        else:
            context += f"**{i}. {res.get('name', 'Документ')}** (релевантность: {res['score']})\n"
        
        context += f"Фрагмент: {res['preview']}\n\n"
    
    context += f"❓ **Вопрос:** {query}\n\n"
    context += "Ответь на вопрос, используя информацию из документов выше. Если информации нет — скажи честно."
    
    # Отправляем в ИИ
    try:
        from core.ai_engine import ask_zeta_sync
        response = ask_zeta_sync(context)
        return response
    except Exception as e:
        return f"⚠️ Ошибка: {e}"


# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_all_documents() -> List[Dict]:
    """Возвращает список всех документов."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, name, path, size, created_at FROM documents ORDER BY created_at DESC"
        ).fetchall()
    return [
        {'id': r[0], 'name': r[1], 'path': r[2], 'size': r[3], 'created_at': r[4]}
        for r in rows
    ]


def get_document(doc_id: int) -> Optional[Dict]:
    """Возвращает документ по ID."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, name, path, content, size, created_at FROM documents WHERE id = ?",
            (doc_id,)
        ).fetchone()
    if row:
        return {'id': row[0], 'name': row[1], 'path': row[2], 'content': row[3], 'size': row[4], 'created_at': row[5]}
    return None


def delete_document(doc_id: int) -> bool:
    """Удаляет документ из базы."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    
    # Удаляем из ChromaDB
    if _collection:
        try:
            _collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass
    
    return True


def clear_all_documents():
    """Удаляет все документы."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM documents")
    
    # Очищаем ChromaDB
    if _collection:
        try:
            _collection.delete(where={})
        except Exception:
            pass


def get_document_stats() -> Dict[str, Any]:
    """Возвращает статистику по документам."""
    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        total_size = conn.execute("SELECT SUM(size) FROM documents").fetchone()[0] or 0
        total_content_len = conn.execute("SELECT SUM(LENGTH(content)) FROM documents").fetchone()[0] or 0
    
    return {
        'total_documents': total,
        'total_chunks': total_chunks,
        'total_size': total_size,
        'total_characters': total_content_len,
    }


# ========== ИНИЦИАЛИЗАЦИЯ ==========
init_rag_db()


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧠 Тест RAG:\n")
    
    # Тест 1: Создание и сохранение
    test_file = "test.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("Zeta — это ИИ-помощник созданный в Узбекистане. Создатель — Samriddin. Zeta умеет отвечать на вопросы, писать код и анализировать изображения.")
    
    content = read_file(test_file)
    print(f"📄 Файл прочитан: {len(content)} символов")
    save_document(test_file, content)
    print("✅ Документ сохранён")
    print("-" * 40)
    
    # Тест 2: Гибридный поиск
    print("📝 Тест 2: Гибридный поиск")
    results = hybrid_search("кто создал Zeta")
    for r in results:
        print(f"Файл: {r.get('name', 'Chunk')}, Источник: {r.get('source')}")
        print(f"Фрагмент: {r['preview']}")
    print("-" * 40)
    
    # Тест 3: RAG-ответ
    print("📝 Тест 3: RAG-ответ")
    answer = ask_with_rag("Кто создал Zeta?")
    print(f"Ответ: {answer}")
    print("-" * 40)
    
    # Тест 4: Статистика
    print("📝 Тест 4: Статистика")
    stats = get_document_stats()
    print(f"Документов: {stats['total_documents']}")
    print(f"Чанков: {stats['total_chunks']}")
    print(f"Размер: {stats['total_size']} байт")
    print("-" * 40)
    
    # Очистка
    os.remove(test_file)
    clear_all_documents()
    print("✅ Тесты завершены")