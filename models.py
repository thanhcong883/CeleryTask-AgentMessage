from typing import Dict, Any, Optional, Union, List
from pydantic import BaseModel, Field


class BotOptions(BaseModel):
    platform: str = Field(
        ...,
        description="Platform type: telegram, zalo, or whatsapp",
        examples=["telegram"],
    )
    token: Optional[str] = Field(
        None,
        description="Access token for the platform (required for Telegram)",
        examples=["7123456789:ABCDefgh-IJKLmnopQRstuvwxYZ12345678"],
    )


class CreateBotRequest(BaseModel):
    botId: Union[str, int] = Field(
        ..., description="Unique ID for the bot", examples=["my_telegram_bot_1"]
    )
    options: BotOptions


class MentionItem(BaseModel):
    offset: int = Field(
        ...,
        description="Starting position of the mention text in the message content",
        examples=[6],
    )
    length: int = Field(
        ...,
        description="Length of the mention text in the message content",
        examples=[5],
    )
    user_id: str = Field(
        ...,
        description="Platform-specific user ID of the mentioned user",
        examples=["84901234567"],
    )
    display_name: Optional[str] = Field(
        None,
        description="Display name shown in the mention text (optional, for reference)",
        examples=["John"],
    )


class Attachment(BaseModel):
    type: str = Field(
        ...,
        description="Type of attachment: image, document, video, audio",
        examples=["image"],
    )
    url: str = Field(
        ...,
        description="Public URL of the attachment",
        examples=["https://example.com/image.jpg"],
    )
    name: Optional[str] = Field(
        None, description="Optional filename", examples=["image.jpg"]
    )
    mimetype: Optional[str] = Field(
        None, description="Optional mimetype", examples=["image/jpeg"]
    )


class SendMessageRequest(BaseModel):

    content: str = Field(
        ..., description="Message content to send", examples=["Hello from the bot!"]
    )
    user_id: Optional[str] = Field(
        None,
        description="Recipient user ID for private messages",
        examples=["123456789"],
    )
    group_id: Optional[str] = Field(
        None,
        description="Recipient group ID for group messages",
        examples=["-987654321"],
    )
    type: str = Field(
        "private", description="Message type: private or group", examples=["private"]
    )
    message_id: Optional[str] = Field(
        None,
        description="Optional internal message ID for tracking and updates",
        examples=["msg_12345"],
    )
    attachments: Optional[List[Attachment]] = Field(
        None,
        description="List of attachments to send",
    )
    reply_to: Optional[str] = Field(
        None,
        description="Platform message ID of the message to reply/quote",
        examples=["3EB0A1B2C3D4E5F6"],
    )
    mentions: Optional[List[MentionItem]] = Field(
        None,
        description="List of user mentions/tags in the message (for group chats)",
    )


class GenericResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    message: Optional[str] = Field(None, examples=["Operation successful"])


class BotStatusResponse(BaseModel):
    status: str = Field(
        ...,
        description="Bot status: up, down, or other platform-specific status",
        examples=["up"],
    )
    platform: str = Field(..., examples=["telegram"])
    details: Optional[Dict[str, Any]] = None
