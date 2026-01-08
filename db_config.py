# Cấu hình MySQL
DB_CONFIG = {
    "host": "123.30.233.86",
    "port": 3308,            
    "user": "strapi_user",         
    "password": "Evgcloud123312##",          
    "database": "strapi_db"  
}

ZALO_ACCESS_TOKEN = "Nky8OlqqI0XOxGbY_3D325pW0sNq9JH8NVOmPw9qEmu6gXuzz2Cg3YEC5M2AL5LKUOztOw02IGzwWancdGzCSds9QsUVBo58UUaSJDnn92a6gHK2tpKfBoYpAH3o3345LhO54hyKCYnTqWmvldnCDtp52W2bMaiBU-5S9DjiGZGmqtLOpMfITZ36RXhK7aqkAxjtDDyKCXmaoo8Ym5Gb4IVQ7tx673mH1eG1VTmQHM8Ec69l_Y8bGHMZ84Nj2WfG4TDCGRHmT51ixL1XiKbjN6UFBb6p7H5LLBycQFHbCs1T_X9rlN9NIcRoNYMjMXytJSGE1ub25pPymJ4lW7802YR0E33POXG88kjA4jOsPZeec2OnoJyDDIo6DotC7WqmCSOx1jLP8suKmo9xw1qm4a60UpTjQ97hSrpxAaW9"
TELEGRAM_BOT_TOKEN = "8590498795:AAGRnVpqG1OjSBieSwJG2hAvU89tVfc8YHM"

REDIS_HOST = "redis.evgcloud.local" 
REDIS_PASSWORD = "redispass"
REDIS_USER = "default" 
REDIS_PORT = 6379
REDIS_URL = f"redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/3"

STRAPI_ACCOUNT = "http://localhost:1337/api/accounts"
STRAPI_CONVERSATION = "http://localhost:1337/api/conversations"
STRAPI_CONVERSATION_MEMBER ="http://localhost:1337/api/conversation-members"
STRAPI_CUSTOMER = "http://localhost:1337/api/customers"
STRAPI_MESSAGE = "http://localhost:1337/api/messages"
STRAPI_PLATFORM = "http://localhost:1337/api/platforms"
STRAPI_TOKEN = "Bearer 40ccabda9b71ee3e776367acd971dcd3f6e759b4439c3e14d78ca7e88a20504dbde0c1260fb71aa5590152c75cf163c888aba5b8c6e724a79ae508b3eac0b8aed09929e3884e24cb00a22154bee4bd8a5dc0a92f3c7e69416fb6b675c1a7f1a3350cca172f570681ea99bc9ec916f4791709dd768a65975d125bb12d6c9ab905"