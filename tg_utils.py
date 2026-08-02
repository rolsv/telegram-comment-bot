import os
import random
import logging
from typing import List, Dict, Optional, Tuple, Set

from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError, FloodWaitError
from telethon.tl.functions.messages import GetDiscussionMessageRequest

from config import GIF_FOLDER, LOG_CHANNEL

# =====================================================
# ================= GIF ==============================
# =====================================================

def get_random_gif():
    if not os.path.isdir(GIF_FOLDER):
        return None
    
    files = [f for f in os.listdir(GIF_FOLDER) if f.lower().endswith(".gif")]
    if not files:
        return None
    
    return os.path.join(GIF_FOLDER, random.choice(files))


def get_gifs_count() -> int:
    if not os.path.isdir(GIF_FOLDER):
        return 0
    return len([f for f in os.listdir(GIF_FOLDER) if f.lower().endswith(".gif")])


# =====================================================
# ================= TELEGRAM ==========================
# =====================================================

async def ensure_joined(client: TelegramClient, channel: str):
    try:
        await client(JoinChannelRequest(channel))
    except UserAlreadyParticipantError:
        pass
    except Exception as e:
        logging.error(f"Ошибка подписки: {e}")


async def send_log_to_tg(text: str, client: Optional[TelegramClient] = None):
    """Отправляет лог в Telegram"""
    logging.info(f"[LOG] {text}")
    
    if not LOG_CHANNEL or not client:
        return
    
    try:
        entity = await client.get_entity(LOG_CHANNEL)
        await client.send_message(entity, f"📝 {text}")
    except ValueError:
        if LOG_CHANNEL.lower() == "me":
            await client.send_message("me", f"📝 {text}")
        else:
            logging.error(f"Не удалось найти чат/пользователя: {LOG_CHANNEL}")
    except Exception as e:
        logging.error(f"Не удалось отправить лог в Telegram: {e}")


async def init_clients(accounts: List[Dict], channels: List[str]) -> List[TelegramClient]:
    os.makedirs("sessions", exist_ok=True)
    clients = []

    for acc in accounts:
        session_path = os.path.join("sessions", acc["session"])
        
        try:
            client = TelegramClient(
                session_path,
                acc["api_id"],
                acc["api_hash"],
                proxy=acc.get("proxy")
            )
            await client.start()
            
            for channel in channels:
                await ensure_joined(client, channel)
            
            clients.append(client)
            logging.info(f"{acc['session']} запущен (роль: {acc.get('role', 'commenter')})")
            
        except Exception as e:
            logging.error(f"{acc['session']} не запустился: {e}")
            continue

    return clients


async def run_client_safe(client: TelegramClient):
    try:
        await client.run_until_disconnected()
    except Exception as e:
        logging.error(f"Клиент упал: {e}")


async def shutdown_clients(clients: List[TelegramClient]):
    logging.info("Начинаю корректное завершение...")
    for client in clients:
        try:
            if client.is_connected():
                await client.disconnect()
                logging.info(f"{client.session.filename} отключен")
        except Exception as e:
            logging.error(f"Ошибка при отключении: {e}")
    logging.info("Все клиенты остановлены")


async def get_discussion_entities_for_all(
    clients: List[TelegramClient],
    channel: str,
    msg_id: int
) -> Dict[TelegramClient, Tuple[object, int]]:
    discussion_entities = {}

    for client in clients:
        try:
            res = await client(GetDiscussionMessageRequest(
                peer=channel,
                msg_id=msg_id
            ))

            if not res.messages or not res.chats:
                continue

            discussion_msg_client = res.messages[0]
            discussion_chat_client = res.chats[0]
            entity = await client.get_entity(discussion_chat_client)
            discussion_entities[client] = (entity, discussion_msg_client.id)

        except Exception as e:
            logging.error(f"{client.session.filename} не может получить discussion: {e}")

    return discussion_entities


async def send_comment_or_gif(
    client: TelegramClient,
    entity,
    reply_to_id: int,
    comment: str,
    gif_probability: float = 0.2
):
    try:
        if random.random() < gif_probability:
            gif_path = get_random_gif()
            if gif_path:
                sent = await client.send_file(
                    entity=entity,
                    file=gif_path,
                    reply_to=reply_to_id
                )
                await send_log_to_tg(f"🎞 {client.session.filename} отправил гиф", client)
                return sent

        sent = await client.send_message(
            entity=entity,
            message=comment,
            reply_to=reply_to_id
        )
        await send_log_to_tg(f"💬 {client.session.filename}:\n{comment}", client)
        return sent

    except FloodWaitError as e:
        logging.error(f"FloodWait у {client.session.filename}: {e}")
        return None
    except Exception as e:
        logging.error(f"Ошибка отправки ({client.session.filename}): {e}")
        return None


async def send_reply_message(
    client: TelegramClient,
    discussion_entities: Dict[TelegramClient, Tuple[object, int]],
    reply_to_id: int,
    text: str
):
    entity_data = discussion_entities.get(client)
    if not entity_data:
        return None

    entity, _ = entity_data

    try:
        sent = await client.send_message(
            entity=entity,
            message=text,
            reply_to=reply_to_id
        )
        await send_log_to_tg(f"↪️ {client.session.filename} ответил:\n{text}", client)
        return sent
    except FloodWaitError as e:
        logging.error(f"FloodWait в диалоге у {client.session.filename}: {e}")
        return None
    except Exception as e:
        logging.error(f"Ошибка ответа ({client.session.filename}): {e}")
        return None