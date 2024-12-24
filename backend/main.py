from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Set, List
import json
from datetime import datetime
import logging
import asyncio
import re
import random
import os
from openai import AsyncOpenAI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化OpenAI客户端
client = AsyncOpenAI(
    api_key="foo",  # 使用空API key，因为我们使用的是本地模型
    base_url="https://api.openai.com/v1/chat/completions"  # 使用本地模型服务地址
)
model = "gpt-4o"

app = FastAPI()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatBot:
    def __init__(self):
        self.name = "小助手"
        self.greetings = [
            "你好！我是AI助手，很高兴见到你~",
            "Hi！我是智能助手，有什么我可以帮你的吗？",
            "你好啊！让我们开始愉快的对话吧！",
        ]
        self.conversation_history: List[dict] = []
        self.system_prompt = """你是一个友好、专业的AI助手。
- 你的回答应该简洁、准确、友好。
- 你会使用适当的表情符号来让对话更生动。
- 你会避免过长的回答，保持对话的流畅性。
- 你会记住用户之前说过的话，保持对话的连贯性。
- 如果用户问题涉及敏感话题，你会礼貌地拒绝回答。
"""

    def get_greeting(self) -> str:
        return random.choice(self.greetings)

    async def get_response(self, username: str, message: str) -> str:
        try:
            # 添加用户消息到历史记录
            self.conversation_history.append({
                "role": "user",
                "content": message
            })
            
            # 保持对话历史在合理范围内
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            # 准备消息列表
            messages = [
                {"role": "system", "content": self.system_prompt},
                *self.conversation_history
            ]
            
            # 调用OpenAI API
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
            )
            
            # 获取回复内容
            reply = response.choices[0].message.content.strip()
            
            # 添加助手回复到历史记录
            self.conversation_history.append({
                "role": "assistant",
                "content": reply
            })
            
            return reply
            
        except Exception as e:
            logger.error(f"Error getting AI response: {str(e)}")
            return random.choice([
                "抱歉，我现在有点累了，能稍后再聊吗？",
                "对不起，我需要休息一下，很快就回来~",
                "不好意思，我现在有点忙，晚点再和你聊天好吗？"
            ])

bot = ChatBot()

def is_valid_username(username: str) -> bool:
    """验证用户名是否有效"""
    if not username or len(username) > 20:
        return False
    # 只允许中文、英文、数字和下划线
    return bool(re.match(r'^[\u4e00-\u9fa5_a-zA-Z0-9]+$', username))

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.usernames: Set[str] = set()
        self.bot_name = bot.name
        self.usernames.add(self.bot_name)  # 将机器人添加到用户列表

    async def connect(self, websocket: WebSocket, username: str) -> bool:
        try:
            await websocket.accept()
            self.active_connections[username] = websocket
            self.usernames.add(username)
            # 如果小助手不在active_connections中，将其添加进去
            if self.bot_name not in self.active_connections:
                self.active_connections[self.bot_name] = None
            return True
        except Exception as e:
            logger.error(f"Error accepting connection for {username}: {str(e)}")
            return False

    async def disconnect(self, username: str):
        if username in self.active_connections:
            try:
                await self.active_connections[username].close()
            except Exception as e:
                logger.error(f"Error closing connection for {username}: {str(e)}")
            finally:
                self.active_connections.pop(username)
                if username != self.bot_name:  # 不要移除机器人
                    self.usernames.remove(username)

    async def broadcast(self, message: dict):
        """广播消息给所有连接的用户"""
        disconnected_users = []
        for username, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {username}: {str(e)}")
                disconnected_users.append(username)
        
        # 清理断开的连接
        for username in disconnected_users:
            await self.disconnect(username)

    async def send_bot_message(self, message: str):
        """发送机器人消息"""
        await self.broadcast({
            "type": "message",
            "username": self.bot_name,
            "content": message,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    async def send_private_message(self, message: dict, from_user: str, to_user: str):
        """发送私聊消息"""
        try:
            # 如果是发给小助手的消息，直接处理
            if to_user == self.bot_name:
                # 获取机器人回复
                bot_reply = await bot.get_response(from_user, message["content"])
                
                # 发送给用户
                sender_ws = self.active_connections[from_user]
                await sender_ws.send_json({
                    "type": "private_message",
                    "from": self.bot_name,
                    "to": from_user,
                    "content": bot_reply,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                return
            
            # 处理其他用户的私聊消息
            if to_user in self.active_connections and self.active_connections[to_user] is not None:
                receiver_ws = self.active_connections[to_user]
                await receiver_ws.send_json({
                    "type": "private_message",
                    "from": from_user,
                    "to": to_user,
                    "content": message["content"],
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                # 同时发送给发送者
                sender_ws = self.active_connections[from_user]
                await sender_ws.send_json({
                    "type": "private_message",
                    "from": from_user,
                    "to": to_user,
                    "content": message["content"],
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                logger.info(f"Private message sent from {from_user} to {to_user}")
            else:
                # 如果接收者不在线，发送错误消息给发送者
                sender_ws = self.active_connections[from_user]
                await sender_ws.send_json({
                    "type": "system",
                    "content": f"用户 {to_user} 不在线，消息发送失败"
                })
        except Exception as e:
            logger.error(f"Error sending private message: {e}")
            # 发送错误消息给发送者
            try:
                sender_ws = self.active_connections[from_user]
                await sender_ws.send_json({
                    "type": "system",
                    "content": "消息发送失败，请稍后重试"
                })
            except:
                pass
                
    async def broadcast_user_list(self):
        """广播在线用户列表"""
        await self.broadcast({
            "type": "users",
            "users": list(self.usernames)
        })

manager = ConnectionManager()

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    logger.info(f"New connection request from {username}")
    
    try:
        # 验证用户名
        if not is_valid_username(username):
            logger.warning(f"Invalid username attempt: {username}")
            await websocket.close(code=1007, reason="用户名只能包含中文、英文、数字和下划线")
            return
        
        # 检查用户名是否已被使用
        if username in manager.usernames:
            logger.warning(f"Duplicate username attempt: {username}")
            await websocket.close(code=1008, reason="用户名已被使用")
            return
        
        # 接受WebSocket连接
        logger.info(f"Accepting connection for {username}")
        success = await manager.connect(websocket, username)
        
        if not success:
            logger.error(f"Failed to establish connection for {username}")
            return
        
        logger.info(f"Connection accepted for {username}")
        
        # 发送用户加入消息
        join_message = {
            "type": "system",
            "content": f"{username} 加入了聊天室",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        await manager.broadcast(join_message)
        
        # 更新在线用户列表
        await manager.broadcast_user_list()
        
        # 机器人发送欢迎消息
        await asyncio.sleep(1)  # 稍微延迟一下，让用户能看到加入消息
        await manager.broadcast({
            "type": "message",
            "username": bot.name,
            "content": bot.get_greeting(),
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
        
        try:
            while True:
                # 设置接收超时
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                except asyncio.TimeoutError:
                    # 发送ping消息保持连接活跃
                    await websocket.send_text('ping')
                    continue
                
                logger.info(f"Received message from {username}: {data}")
                
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from {username}: {data}")
                    continue
                
                if not isinstance(message, dict) or 'content' not in message:
                    logger.warning(f"Invalid message format from {username}: {message}")
                    continue
                
                content = message['content'].strip()
                if not content:
                    continue
                
                # 处理私聊消息
                if "isPrivate" in message and message["isPrivate"] and "to" in message:
                    await manager.send_private_message(message, username, message["to"])
                else:
                    # 处理群聊消息
                    await manager.broadcast({
                        "type": "message",
                        "username": username,
                        "content": content,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    
                    # 如果消息中包含@小助手，或者是私聊小助手的消息，让机器人回复
                    if bot.name in content or (message.get("isPrivate") and message.get("to") == bot.name):
                        try:
                            # 获取机器人回复
                            bot_reply = await bot.get_response(username, content)
                            # 发送机器人回复
                            await manager.broadcast({
                                "type": "message",
                                "username": bot.name,
                                "content": bot_reply,
                                "timestamp": datetime.now().strftime("%H:%M:%S")
                            })
                        except Exception as e:
                            logger.error(f"Error getting bot response: {str(e)}")
                    
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for {username}")
        except Exception as e:
            logger.error(f"Error handling messages for {username}: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in websocket connection for {username}: {str(e)}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass
    
    finally:
        # 清理用户连接
        await manager.disconnect(username)
        logger.info(f"Cleaned up connection for {username}")
        
        try:
            # 发送用离开消息
            leave_message = {
                "type": "system",
                "content": f"{username} 离开了聊天室",
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            await manager.broadcast(leave_message)
            
            # 更新在线用户列表
            await manager.broadcast_user_list()
        except Exception as e:
            logger.error(f"Error in cleanup for {username}: {str(e)}")

@app.get("/")
async def root():
    return {
        "status": "running",
        "users_count": len(manager.usernames),
        "server_time": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "users_count": len(manager.usernames),
        "connections_count": len(manager.active_connections)
    }

if __name__ == "__main__":
    # 检查OpenAI API密钥
    if not os.getenv('OPENAI_API_KEY'):
        logger.warning("OPENAI_API_KEY not found in environment variables!")
        logger.warning("Bot will use fallback responses.")
    
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    ) 