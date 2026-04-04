"""Telegram message listener for OrchestraThreads."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


class TelegramListener:
    """Listens to incoming Telegram messages and forwards them to secretary agent."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: str | None = None,
        session_file: str | None = None,
        on_message: Callable[[dict], Awaitable[None]] | None = None,
    ):
        """
        Initialize Telegram listener.

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_string: Optional session string for authentication
            session_file: Optional path to session file
            on_message: Async callback for new messages
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.session_file = session_file
        self.client: TelegramClient | None = None
        self.on_message = on_message

    def _create_session(self):
        """Create Telegram session from string or file."""
        if self.session_string:
            session = StringSession(self.session_string)
            logger.info("Using session string from environment")
            return session
        elif self.session_file:
            session = self.session_file
            logger.info(f"Using session file: {self.session_file}")
            return session
        else:
            session = "sessions/telegram.session"
            Path("sessions").mkdir(exist_ok=True)
            logger.info(f"Using default session file: {session}")
            return session

    async def start(self):
        """Start the Telegram client and begin listening."""
        session = self._create_session()

        self.client = TelegramClient(
            session,
            self.api_id,
            self.api_hash,
        )

        logger.info("Starting Telegram client...")

        try:
            await self.client.start()

            me = await self.client.get_me()
            logger.info(f"Logged in as: {me.first_name} (ID: {me.id})")

        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)
            raise

        # Print session string for first run
        if not self.session_string and isinstance(session, str):
            try:
                session_string = self.client.session.save()
                if session_string:
                    logger.info("Session authenticated successfully!")
                    logger.info(f"Save this to TELEGRAM_SESSION_STRING: {session_string}")
            except Exception as e:
                logger.warning(f"Could not save session string: {e}")

        # Register event handlers for new messages
        @self.client.on(events.NewMessage(incoming=True))
        async def handler_incoming(event):
            await self._handle_message(event)

        @self.client.on(events.NewMessage(outgoing=True))
        async def handler_outgoing(event):
            await self._handle_message(event)

        logger.info("Telegram listener started and waiting for messages...")

        # Keep the client running
        await self.client.run_until_disconnected()

    async def _handle_message(self, event):
        """Handle incoming message event."""
        try:
            message = event.message
            sender = await event.get_sender()
            chat = await event.get_chat()

            message_data = await self._extract_message_data(message, sender, chat)

            logger.info(
                f"Received message from {message_data['sender_name']} "
                f"in {message_data['chat_name']}: {message_data['text'][:50]}..."
            )

            if self.on_message:
                await self.on_message(message_data)

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

    async def _extract_message_data(self, message, sender, chat) -> dict:
        """Extract message data into a dictionary."""
        # Extract chat info
        chat_id = None
        if hasattr(message, "peer_id") and message.peer_id:
            peer_id = message.peer_id
            if hasattr(peer_id, "channel_id"):
                chat_id = peer_id.channel_id
            elif hasattr(peer_id, "user_id"):
                chat_id = peer_id.user_id
            elif hasattr(peer_id, "chat_id"):
                chat_id = peer_id.chat_id

        chat_name = "Unknown Chat"
        if chat:
            if hasattr(chat, "title"):
                chat_name = chat.title
            elif hasattr(chat, "first_name"):
                chat_name = chat.first_name
                if hasattr(chat, "last_name") and chat.last_name:
                    chat_name += f" {chat.last_name}"

        # Extract sender info
        sender_name = "Unknown"
        username = None
        user_id = None

        if sender:
            if hasattr(sender, "id"):
                user_id = str(sender.id)

            if hasattr(sender, "username") and sender.username:
                username = sender.username

            if hasattr(sender, "first_name") and sender.first_name:
                sender_name = sender.first_name
                if hasattr(sender, "last_name") and sender.last_name:
                    sender_name += f" {sender.last_name}"
            elif hasattr(sender, "title"):
                sender_name = sender.title
            elif username:
                sender_name = f"@{username}"

        # Extract message text
        text = message.message or ""

        # Extract timestamp
        timestamp = message.date.isoformat() if message.date else None

        return {
            "chat_id": str(chat_id) if chat_id else "unknown",
            "chat_name": chat_name,
            "message_id": message.id,
            "sender_name": sender_name,
            "username": username,
            "user_id": user_id,
            "text": text,
            "timestamp": timestamp,
        }

    async def stop(self):
        """Stop the Telegram client."""
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram client disconnected")
