import asyncio
import logging
import random
from typing import Set, List, Tuple

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDiscussionMessageRequest

from config import (
    CHANNELS, ACCOUNTS, MIN_POST_LENGTH,
    POST_DELAY, BETWEEN_COMMENTS_DELAY,
    COMMENT_PROBABILITY, DIALOG_PROBABILITY,
    DIALOG_MESSAGES_RANGE, DIALOG_DELAY_RANGE,
    ROOT_COMMENTS_RANGE, GIF_PROBABILITY
)
from ai_utils import generate_comment
from tg_utils import (
    init_clients, run_client_safe, shutdown_clients,
    get_discussion_entities_for_all, send_comment_or_gif,
    send_reply_message, send_log_to_tg, ensure_joined
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

processed_posts: Set[int] = set()
clients: List[TelegramClient] = []
watcher_clients: List[TelegramClient] = []
commenter_clients: List[TelegramClient] = []


def choose_root_comment_clients() -> List[TelegramClient]:
    available = commenter_clients[:]
    random.shuffle(available)

    if ROOT_COMMENTS_RANGE:
        min_c, max_c = ROOT_COMMENTS_RANGE
        count = random.randint(min_c, min(max_c, len(available)))
        return available[:count]

    selected = [c for c in available if random.random() <= COMMENT_PROBABILITY]
    if not selected and available:
        selected.append(random.choice(available))

    return selected


async def run_dialogue_chain(
    post_text: str,
    discussion_entities: dict,
    sent_messages: List[Tuple[TelegramClient, object]],
    used_words_under_post: Set[str]
):
    if len(sent_messages) < 1 or random.random() >= DIALOG_PROBABILITY:
        return

    available_clients = [c for c in commenter_clients if c in discussion_entities]
    if len(available_clients) < 2:
        return

    dialog_len = random.randint(DIALOG_MESSAGES_RANGE[0], DIALOG_MESSAGES_RANGE[1])
    logging.info(f"Запуск диалога на {dialog_len} сообщений")

    last_client, last_message = random.choice(sent_messages)
    last_text = getattr(last_message, "text", "") or ""
    reply_to_id = last_message.id

    participants_pool = available_clients[:]
    random.shuffle(participants_pool)
    active_participants = participants_pool[:max(2, min(4, len(participants_pool)))]

    for _ in range(dialog_len):
        possible_speakers = [c for c in active_participants if c != last_client]
        if not possible_speakers:
            possible_speakers = [c for c in available_clients if c != last_client]
        if not possible_speakers:
            break

        speaker = random.choice(possible_speakers)
        reply_text = await generate_comment(post_text, used_words_under_post, last_text)

        sent = await send_reply_message(speaker, discussion_entities, reply_to_id, reply_text)
        if not sent:
            continue

        last_client = speaker
        last_message = sent
        last_text = getattr(sent, "text", "") or reply_text
        reply_to_id = sent.id

        await asyncio.sleep(random.randint(*DIALOG_DELAY_RANGE))

    logging.info("Диалог завершён")


def create_event_handler(channel: str):
    @events.register(events.NewMessage(chats=channel))
    async def handler(event):
        try:
            msg = event.message
            logging.info(f"[EVENT] channel={channel} id={msg.id}")

            post_key = f"{channel}_{msg.id}"
            if post_key in processed_posts:
                return
            processed_posts.add(post_key)

            await asyncio.sleep(random.randint(20, 60))
            logging.info(f"Новый пост в {channel}: {msg.id}")

            if not msg.text or len(msg.text) < MIN_POST_LENGTH:
                logging.info("Пропуск: слишком короткий пост")
                return

        except Exception as e:
            logging.exception(f"Ошибка в обработчике: {e}")
            return

        await asyncio.sleep(random.randint(*POST_DELAY))

        # Получаем discussion entities
        logging.info("Получение discussion entity...")
        discussion_entities = await get_discussion_entities_for_all(
            commenter_clients, channel, msg.id  # Используем commenter_clients
        )
        
        logging.info(f"Получено discussion_entities: {len(discussion_entities)}")
        for client, data in discussion_entities.items():
            logging.info(f"  - {client.session.filename}: entity={data[0]}, reply_id={data[1]}")

        if not discussion_entities:
            logging.error("❌ Не удалось получить discussion entity")
            return

        used_words_under_post: Set[str] = set()
        sent_messages: List[Tuple[TelegramClient, object]] = []

        # Основные комментарии
        root_clients = choose_root_comment_clients()
        logging.info(f"Будет отправлено {len(root_clients)} комментариев")
        
        for client in root_clients:
            entity_data = discussion_entities.get(client)
            if not entity_data:
                logging.warning(f"Нет entity для {client.session.filename}")
                continue

            entity, reply_id = entity_data
            logging.info(f"Отправка от {client.session.filename}")
            
            comment = await generate_comment(msg.text, used_words_under_post)
            logging.info(f"Комментарий: {comment}")

            sent = await send_comment_or_gif(
                client, entity, reply_id, comment, GIF_PROBABILITY
            )

            if sent:
                sent_messages.append((client, sent))
                logging.info(f"✅ Комментарий отправлен ({client.session.filename})")
            else:
                logging.error(f"❌ Не удалось отправить комментарий ({client.session.filename})")

            await asyncio.sleep(random.randint(*BETWEEN_COMMENTS_DELAY))

        # Диалог
        if sent_messages:
            await run_dialogue_chain(
                msg.text, discussion_entities, sent_messages, used_words_under_post
            )
        else:
            logging.info("Нет отправленных комментариев для диалога")
    
    return handler


async def main():
    global clients, watcher_clients, commenter_clients

    clients = await init_clients(ACCOUNTS, CHANNELS)
    if not clients:
        logging.error("Нет ни одного успешно запущенного клиента")
        return

    for acc, client in zip(ACCOUNTS, clients):
        role = acc.get("role", "commenter")
        if role == "watcher":
            watcher_clients.append(client)
        else:
            commenter_clients.append(client)

    if not watcher_clients:
        logging.error("Нет watcher аккаунтов для отслеживания постов")
        return

    if not commenter_clients:
        logging.error("Нет commenter аккаунтов для комментирования")
        return

    logging.info(f"Watcher аккаунты: {[c.session.filename for c in watcher_clients]}")
    logging.info(f"Commenter аккаунты: {[c.session.filename for c in commenter_clients]}")

    for channel in CHANNELS:
        if channel.strip():
            handler = create_event_handler(channel.strip())
            watcher_clients[0].add_event_handler(handler)
            logging.info(f"Добавлен обработчик для канала: {channel}")

    tasks = [asyncio.create_task(run_client_safe(c)) for c in clients]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logging.info("Таски отменены")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await shutdown_clients(clients)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановка по Ctrl+C")