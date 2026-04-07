from typing import Dict, Any, Optional, Union, List
from pydantic import BaseModel, Field

class BotOptions(BaseModel):
    platform: str = Field(..., description="Platform type: telegram, zalo, or whatapps", examples=["telegram"])
    token: Optional[str] = Field(None, description="Access token for the platform (required for Telegram)", examples=["7123456789:ABCDefgh-IJKLmnopQRstuvwxYZ12345678"])

class CreateBotRequest(BaseModel):
    botId: Union[str, int] = Field(..., description="Unique ID for the bot", examples=["my_telegram_bot_1"])
    options: BotOptions

class SendMessageRequest(BaseModel):
    content: str = Field(..., description="Message content to send", examples=["Hello from the bot!"])
    user_id: Optional[str] = Field(None, description="Recipient user ID for private messages", examples=["123456789"])
    group_id: Optional[str] = Field(None, description="Recipient group ID for group messages", examples=["-987654321"])
    type: str = Field("private", description="Message type: private or group", examples=["private"])
    message_id: Optional[str] = Field(None, description="Optional internal message ID for tracking and updates", examples=["msg_12345"])

class GenericResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    message: Optional[str] = Field(None, examples=["Operation successful"])

class BotStatusResponse(BaseModel):
    status: str = Field(..., description="Bot status: up, down, or other platform-specific status", examples=["up"])
    platform: str = Field(..., examples=["telegram"])
    details: Optional[Dict[str, Any]] = None
