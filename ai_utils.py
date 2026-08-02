import asyncio
import logging
import random
import re
from typing import Optional, Set, List

from network_tools import NetworkToolsAPI
from config import OPENAI_API_KEY, AI_MODEL, MAX_COMMENT_CHARS, COMMENT_GENERATION_TRIES

# =====================================================
# ================= AI ================================
# =====================================================

ai = NetworkToolsAPI(OPENAI_API_KEY)

# Загружаем примеры
def load_examples() -> List[str]:
    try:
        with open("comment_examples.txt", "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
            return [x for x in lines if x]
    except Exception:
        return []

COMMENT_STYLE_EXAMPLES = load_examples()

COMMON_WORDS = {
    "ну", "вот", "это", "как", "так", "там", "тут", "для", "или", "что", "чето",
    "прям", "типа", "мда", "жесть", "бля", "пздц", "пиздец", "нахуй", "сука",
    "она", "они", "его", "ее", "её", "мне", "тебе", "вам", "нас", "вас", "мои",
    "твой", "мой", "если", "уже", "ещё", "еще", "просто", "тоже", "надо",
    "есть", "нет", "да", "не", "на", "в", "с", "и", "а", "но", "по", "за", "от",
    "до", "из", "под", "к", "о", "об", "же", "ли"
}

FALLBACK_COMMENTS = [
    "мда жестко", "ну это сильно конечно", "ахах ну бывает",
    "чета сомнительно", "не ну это перебор", "жесть конечно",
    "по факту", "вообще странно", "норм тема кстати",
    "ну такое если честно", "орнул с этого", "да уж"
]


def sample_examples(n: int = 6) -> str:
    if not COMMENT_STYLE_EXAMPLES:
        return ""
    picked = random.sample(COMMENT_STYLE_EXAMPLES, min(n, len(COMMENT_STYLE_EXAMPLES)))
    return "\n".join(f"- {x}" for x in picked)


def ai_request(prompt: str, chat_history=None):
    if chat_history is None:
        chat_history = []

    try:
        return ai.chatgpt_api(
            prompt=prompt,
            model=AI_MODEL,
            chat_history=chat_history
        )
    except Exception as e:
        logging.error(f"Ошибка вызова модели {AI_MODEL}: {e}")
        raise


def choose_persona():
    personas = [
        {"name": "skeptic", "style": "скептичный, чуть недовольный, иногда ворчит", "extra": "любит короткие фразы"},
        {"name": "ironic", "style": "ироничный, с легким стебом", "extra": "звучит как человек, который не особо удивлен"},
        {"name": "casual", "style": "обычный телеграм чел, простой разговорный стиль", "extra": "пишет естественно"},
        {"name": "hype", "style": "чуть хайповый, эмоциональный", "extra": "может радоваться, удивляться"},
        {"name": "smartass", "style": "делает вид что шарит, но пишет по-простому", "extra": "вставляет мнение"},
        {"name": "lazy", "style": "ленивый, короткий, суховатый", "extra": "любит очень короткие комментарии"},
    ]
    return random.choice(personas)


def swear_mode():
    r = random.random()
    if r < 0.35:
        return "без мата"
    elif r < 0.80:
        return "можно одно матерное слово"
    else:
        return "можно немного мата"


def choose_comment_length():
    r = random.random()
    if r < 0.40:
        return (2, 4)
    elif r < 0.80:
        return (4, 7)
    else:
        return (7, 11)


def choose_reaction_mode():
    modes = [
        "реакция с сомнением", "реакция с одобрением", "реакция с насмешкой",
        "реакция когда разрывает от эмоций", "реакция с удивлением",
        "реакция офигел", "реакция спорные эмоции",
    ]
    return random.choice(modes)


def normalize_comment(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^комментарий\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("«", "").replace("»", "").replace('"', "")
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(вот\s+)?вариант\s+комментария\s*:\s*", "", text, flags=re.IGNORECASE)
    
    parts = [p.strip() for p in re.split(r"[\n]+", text) if p.strip()]
    if parts:
        text = parts[0]
    
    if len(text) > MAX_COMMENT_CHARS:
        cut = text[:MAX_COMMENT_CHARS].rstrip()
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut
    
    return text.strip(" .!?\t")


def humanize_comment(text: str) -> str:
    text = text.strip().lower()
    
    if random.random() < 0.35:
        text = text.replace(",", "")
    if random.random() < 0.85:
        text = text.rstrip(".!?")
    if random.random() < 0.10:
        text = re.sub(r"\bчто\b", "чо", text)
    if random.random() < 0.10:
        text = re.sub(r"\bчто-то\b", "чета", text)
    if random.random() < 0.08:
        text = text.replace("сейчас", "щас", 1)
    if random.random() < 0.08:
        text = text.replace("тебя", "тя", 1)
    
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def clean_words(text: str) -> Set[str]:
    words = re.findall(r"[а-яa-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in COMMON_WORDS}


def is_too_similar(comment: str, used_words: Set[str]) -> bool:
    words = clean_words(comment)
    if not words:
        return False
    overlap = words & used_words
    return len(overlap) >= 2


def remember_comment_words(comment: str, used_words: Set[str]):
    used_words.update(clean_words(comment))


def build_prompt(post_text: str, reply_to_text: Optional[str] = None) -> str:
    length_min, length_max = choose_comment_length()
    swear_instruction = swear_mode()
    examples = sample_examples()
    persona = choose_persona()
    reaction_mode = choose_reaction_mode()

    if not examples:
        examples = "- мда\n- жесть конечно\n- ну это сильно"

    if reply_to_text:
        context_block = f"""контекст поста:
{post_text}

сообщение, на которое надо ответить:
{reply_to_text}
"""
    else:
        context_block = f"""пост:
{post_text}
"""

    return f"""
Ты русский школьник, напиши ОДИН комментарий как живой человек из русского телеграм чата.

- характер комментария: {persona['style']}

правила:
- только русский язык
- длина {length_min}-{length_max} слов
- без заглавных
- без эмодзи
- стиль живой, разговорный, слегка небрежный
- иногда можно пропустить запятую или написать чуть кривовато
- не пиши слишком грамотно и литературно
- {swear_instruction}
- комментарий должен относиться к теме
- не пересказывай пост дословно
- не пиши пояснений
- не пиши несколько вариантов
- верни только сам комментарий

характер:
- {persona["style"]}
- {persona["extra"]}

тип реакции:
- {reaction_mode}

примеры нужного вайба:
{examples}

{context_block}

комментарий:
""".strip()


async def generate_candidate(post_text: str, reply_to_text: Optional[str] = None) -> Optional[str]:
    prompt = build_prompt(post_text=post_text, reply_to_text=reply_to_text)

    try:
        response = await asyncio.to_thread(ai_request, prompt, [])
        text = response.response.text.strip()
        text = normalize_comment(text)
        text = humanize_comment(text)

        if not text or len(text) < 4 or text.count("\n") > 0:
            return None

        return text
    except Exception as e:
        logging.error(f"Ошибка генерации: {e}")
        return None


def pick_fallback(reply_to_text: Optional[str] = None) -> str:
    if reply_to_text:
        reply_fallbacks = [
            "ахах ну да", "да это база", "не ну тут факт",
            "согласен кстати", "ну ты прав", "тоже так думаю", "вот именно"
        ]
        return random.choice(reply_fallbacks)
    return random.choice(FALLBACK_COMMENTS)


async def generate_comment(post_text: str, used_words: Set[str], reply_to_text: Optional[str] = None) -> str:
    for _ in range(COMMENT_GENERATION_TRIES):
        comment = await generate_candidate(post_text=post_text, reply_to_text=reply_to_text)
        if not comment or len(comment) < 5 or is_too_similar(comment, used_words):
            continue
        remember_comment_words(comment, used_words)
        return comment

    fallback = pick_fallback(reply_to_text=reply_to_text)
    remember_comment_words(fallback, used_words)
    return fallback