import os
import json
import uuid
import base64
import sys
import inspect
from loguru import logger
import os
import asyncio
import time
import aiohttp
import io
from datetime import datetime
from functools import partial

from quart import Quart, request, jsonify, Response
from quart_cors import cors
import cloudscraper
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "MODELS": {
        'grok-2': 'grok-latest',
        'grok-2-imageGen': 'grok-latest',
        'grok-2-search': 'grok-latest',
        "grok-3": "grok-3",
        "grok-3-search": "grok-3",
        "grok-3-imageGen": "grok-3",
        "grok-3-deepsearch": "grok-3",
        "grok-3-reasoning": "grok-3"
    },
    "API": {
        "BASE_URL": "https://grok.com",
        "API_KEY": os.getenv("API_KEY", "sk-123456"),
        "IS_TEMP_CONVERSATION": os.getenv("IS_TEMP_CONVERSATION", "false").lower() == "true",
        "PICGO_KEY": os.getenv("PICGO_KEY", None),  # 想要流式生图的话需要填入这个PICGO图床的key
        "TUMY_KEY": os.getenv("TUMY_KEY", None),  # 想要流式生图的话需要填入这个TUMY图床的key
        "IS_CUSTOM_SSO": os.getenv("IS_CUSTOM_SSO", "false").lower() == "true"
    },
    "SERVER": {
        "PORT": int(os.getenv("PORT", 3000))
    },
    "RETRY": {
        "MAX_ATTEMPTS": 2 
    },
    "SHOW_THINKING": os.getenv("SHOW_THINKING", "false").lower() == "true",
    "IS_THINKING": False,
    "IS_IMG_GEN": False,
    "IS_IMG_GEN2": False,
    "ISSHOW_SEARCH_RESULTS": os.getenv("ISSHOW_SEARCH_RESULTS", "true").lower() == "true"
}

class Logger:
    def __init__(self, level="INFO", colorize=True, format=None):
        # 移除默认的日志处理器
        logger.remove()

        if format is None:
            format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{extra[filename]}</cyan>:<cyan>{extra[function]}</cyan>:<cyan>{extra[lineno]}</cyan> | "
                "<level>{message}</level>"
            )

        logger.add(
            sys.stderr, 
            level=level, 
            format=format,
            colorize=colorize,
            backtrace=True,
            diagnose=True
        )

        self.logger = logger

    def _get_caller_info(self):
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back.f_back
            full_path = caller_frame.f_code.co_filename
            function = caller_frame.f_code.co_name
            lineno = caller_frame.f_lineno
            
            filename = os.path.basename(full_path)
            
            return {
                'filename': filename,
                'function': function,
                'lineno': lineno
            }
        finally:
            del frame 

    def info(self, message, source="API"):
        caller_info = self._get_caller_info()
        self.logger.bind(**caller_info).info(f"[{source}] {message}")
        
    def error(self, message, source="API"):
        caller_info = self._get_caller_info()
        
        if isinstance(message, Exception):
            self.logger.bind(**caller_info).exception(f"[{source}] {str(message)}")
        else:
            self.logger.bind(**caller_info).error(f"[{source}] {message}")
    
    def warning(self, message, source="API"):
        caller_info = self._get_caller_info()
        self.logger.bind(**caller_info).warning(f"[{source}] {message}")
    
    def debug(self, message, source="API"):
        caller_info = self._get_caller_info()
        self.logger.bind(**caller_info).debug(f"[{source}] {message}")

    async def request_logger(self, request):
        caller_info = self._get_caller_info()
        self.logger.bind(**caller_info).info(f"请求: {request.method} {request.path}", "Request")

logger = Logger(level="INFO")

class AuthTokenManager:
    def __init__(self):
        self.token_model_map = {}
        self.expired_tokens = set()
        self.token_status_map = {}
        self.token_reset_switch = False
        self.token_reset_timer = None
        self.is_custom_sso = os.getenv("IS_CUSTOM_SSO", "false").lower() == "true"

        self.model_config = {
            "grok-2": {
                "RequestFrequency": 2,
                "ExpirationTime": 1 * 60 * 60  
            },
            "grok-3": {
                "RequestFrequency": 20,
                "ExpirationTime": 2 * 60 * 60  #
            },
            "grok-3-deepsearch": {
                "RequestFrequency": 10,
                "ExpirationTime": 24 * 60 * 60  
            },
            "grok-3-reasoning": {
                "RequestFrequency": 10,
                "ExpirationTime": 24 * 60 * 60  
            }
        }
        
    async def add_token(self, token):
        sso = token.split("sso=")[1].split(";")[0]
        for model in self.model_config.keys():
            if model not in self.token_model_map:
                self.token_model_map[model] = []
                
            if sso not in self.token_status_map:
                self.token_status_map[sso] = {}
                
            existing_token_entry = next((entry for entry in self.token_model_map[model] 
                                         if entry.get("token") == token), None)
                
            if not existing_token_entry:
                self.token_model_map[model].append({
                    "token": token,
                    "RequestCount": 0,
                    "AddedTime": time.time(),
                    "StartCallTime": None
                })
                
                if model not in self.token_status_map[sso]:
                    self.token_status_map[sso][model] = {
                        "isValid": True,
                        "invalidatedTime": None,
                        "totalRequestCount": 0
                    }
        logger.info(f"添加令牌成功: {token}", "TokenManager")
        
    async def set_token(self, token):
        models = list(self.model_config.keys())
        for model in models:
            self.token_model_map[model] = [{
                "token": token,
                "RequestCount": 0,
                "AddedTime": time.time(),
                "StartCallTime": None
            }]
        
        sso = token.split("sso=")[1].split(";")[0]
        self.token_status_map[sso] = {}
        for model in models:
            self.token_status_map[sso][model] = {
                "isValid": True,
                "invalidatedTime": None,
                "totalRequestCount": 0
            }
        logger.info(f"设置令牌成功: {token}", "TokenManager")
        
    async def delete_token(self, token):
        try:
            sso = token.split("sso=")[1].split(";")[0]
            
            for model in self.token_model_map:
                self.token_model_map[model] = [
                    entry for entry in self.token_model_map[model]
                    if entry.get("token") != token
                ]
                
            if sso in self.token_status_map:
                del self.token_status_map[sso]
                
            logger.info(f"令牌已成功移除: {token}", "TokenManager")
            return True
        except Exception as error:
            logger.error(f"令牌删除失败: {error}", "TokenManager")
            return False
            
    def get_next_token_for_model(self, model_id):
        normalized_model = self.normalize_model_name(model_id)
        
        if normalized_model not in self.token_model_map or not self.token_model_map[normalized_model]:
            return None
            
        token_entry = self.token_model_map[normalized_model][0]
        
        if token_entry:
            if self.is_custom_sso:
                return token_entry["token"]
            
            if token_entry["StartCallTime"] is None:
                token_entry["StartCallTime"] = time.time()
                
            if not self.token_reset_switch:
                self.start_token_reset_process()
                self.token_reset_switch = True
                
            token_entry["RequestCount"] += 1
            
            if token_entry["RequestCount"] > self.model_config[normalized_model]["RequestFrequency"]:
                self.remove_token_from_model(normalized_model, token_entry["token"])
                if not self.token_model_map[normalized_model]:
                    return None
                next_token_entry = self.token_model_map[normalized_model][0]
                return next_token_entry["token"] if next_token_entry else None
            
            sso = token_entry["token"].split("sso=")[1].split(";")[0]
            if sso in self.token_status_map and normalized_model in self.token_status_map[sso]:
                if token_entry["RequestCount"] == self.model_config[normalized_model]["RequestFrequency"]:
                    self.token_status_map[sso][normalized_model]["isValid"] = False
                    self.token_status_map[sso][normalized_model]["invalidatedTime"] = time.time()
                
                self.token_status_map[sso][normalized_model]["totalRequestCount"] += 1
                
            return token_entry["token"]
        
        return None
        
    def remove_token_from_model(self, model_id, token):
        normalized_model = self.normalize_model_name(model_id)
        
        if normalized_model not in self.token_model_map:
            logger.error(f"模型 {normalized_model} 不存在", "TokenManager")
            return False
            
        model_tokens = self.token_model_map[normalized_model]
        token_index = -1
        
        for i, entry in enumerate(model_tokens):
            if entry["token"] == token:
                token_index = i
                break
                
        if token_index != -1:
            removed_token_entry = model_tokens.pop(token_index)
            self.expired_tokens.add((
                removed_token_entry["token"],
                normalized_model,
                time.time()
            ))
            
            if not self.token_reset_switch:
                self.start_token_reset_process()
                self.token_reset_switch = True
                
            logger.info(f"模型{model_id}的令牌已失效，已成功移除令牌: {token}", "TokenManager")
            return True
            
        logger.error(f"在模型 {normalized_model} 中未找到 token: {token}", "TokenManager")
        return False
        
    def get_expired_tokens(self):
        return list(self.expired_tokens)
        
    def normalize_model_name(self, model):
        if model.startswith('grok-') and 'deepsearch' not in model and 'reasoning' not in model:
            return '-'.join(model.split('-')[:2])
        return model
        
    def get_token_count_for_model(self, model_id):
        normalized_model = self.normalize_model_name(model_id)
        return len(self.token_model_map.get(normalized_model, []))
        
    def get_remaining_token_request_capacity(self):
        remaining_capacity_map = {}
        
        for model in self.model_config:
            model_tokens = self.token_model_map.get(model, [])
            model_request_frequency = self.model_config[model]["RequestFrequency"]
            
            total_used_requests = sum(entry.get("RequestCount", 0) for entry in model_tokens)
            remaining_capacity = (len(model_tokens) * model_request_frequency) - total_used_requests
            remaining_capacity_map[model] = max(0, remaining_capacity)
            
        return remaining_capacity_map
        
    def get_token_array_for_model(self, model_id):
        normalized_model = self.normalize_model_name(model_id)
        return self.token_model_map.get(normalized_model, [])
        
    def start_token_reset_process(self):
        if hasattr(self, '_reset_task') and self._reset_task:
            pass
        else:
            self._reset_task = asyncio.create_task(self._token_reset_worker())

    async def _token_reset_worker(self):
        while True:
            try:
                current_time = time.time()
                
                expired_tokens_to_remove = set()
                for token_info in self.expired_tokens:
                    token, model, expired_time = token_info
                    expiration_time = self.model_config[model]["ExpirationTime"]
                    
                    if current_time - expired_time >= expiration_time:
                        if not any(entry["token"] == token for entry in self.token_model_map[model]):
                            self.token_model_map[model].append({
                                "token": token,
                                "RequestCount": 0,
                                "AddedTime": current_time,
                                "StartCallTime": None
                            })
                            
                        sso = token.split("sso=")[1].split(";")[0]
                        if sso in self.token_status_map and model in self.token_status_map[sso]:
                            self.token_status_map[sso][model]["isValid"] = True
                            self.token_status_map[sso][model]["invalidatedTime"] = None
                            self.token_status_map[sso][model]["totalRequestCount"] = 0
                            
                        expired_tokens_to_remove.add(token_info)
                
                for token_info in expired_tokens_to_remove:
                    self.expired_tokens.remove(token_info)
                
                for model in self.model_config:
                    if model not in self.token_model_map:
                        continue
                        
                    for token_entry in self.token_model_map[model]:
                        if token_entry["StartCallTime"] is None:
                            continue
                            
                        expiration_time = self.model_config[model]["ExpirationTime"]
                        if current_time - token_entry["StartCallTime"] >= expiration_time:
                            sso = token_entry["token"].split("sso=")[1].split(";")[0]
                            if sso in self.token_status_map and model in self.token_status_map[sso]:
                                self.token_status_map[sso][model]["isValid"] = True
                                self.token_status_map[sso][model]["invalidatedTime"] = None
                                self.token_status_map[sso][model]["totalRequestCount"] = 0
                                
                            token_entry["RequestCount"] = 0
                            token_entry["StartCallTime"] = None
                        
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"令牌重置过程中出错: {e}", "TokenManager")
                await asyncio.sleep(3600)
                
    def get_all_tokens(self):
        all_tokens = set()
        for model_tokens in self.token_model_map.values():
            for entry in model_tokens:
                all_tokens.add(entry["token"])
        return list(all_tokens)
        
    def get_token_status_map(self):
        return self.token_status_map

token_manager = AuthTokenManager()

async def initialize_tokens():
    sso_array = os.getenv("SSO", "").split(',')
    logger.info("开始加载令牌", "Server")
    
    for sso in sso_array:
        if sso.strip(): 
            await token_manager.add_token(f"sso-rw={sso};sso={sso}")
    
    logger.info(f"成功加载令牌: {json.dumps(token_manager.get_all_tokens(), indent=2)}", "Server")
    logger.info(f"令牌加载完成，共加载: {len(token_manager.get_all_tokens())}个令牌", "Server")
    logger.info("初始化完成", "Server")

class Utils:
    @staticmethod
    async def organize_search_results(search_results):
        if not search_results or "results" not in search_results:
            return ''

        results = search_results["results"]
        formatted_results = []
        
        for index, result in enumerate(results):
            title = result.get("title", "未知标题")
            url = result.get("url", "#")
            preview = result.get("preview", "无预览内容")
            
            formatted_result = f"\r\n<details><summary>资料[{index}]: {title}</summary>\r\n{preview}\r\n\n[Link]({url})\r\n</details>"
            formatted_results.append(formatted_result)
            
        return '\n\n'.join(formatted_results)
    
    @staticmethod
    async def run_in_executor(func, *args, **kwargs):
        return await asyncio.get_event_loop().run_in_executor(
            None, partial(func, *args, **kwargs)
        )

class GrokApiClient:
    def __init__(self, model_id):
        if model_id not in CONFIG["MODELS"]:
            raise ValueError(f"不支持的模型: {model_id}")
        self.model = model_id
        self.model_id = CONFIG["MODELS"][model_id]
        self.scraper = cloudscraper.create_scraper()
        
    def process_message_content(self, content):
        if isinstance(content, str):
            return content
        return None
        
    def get_image_type(self, base64_string):
        mime_type = 'image/jpeg'
        if 'data:image' in base64_string:
            import re
            matches = re.match(r'data:([a-zA-Z0-9]+\/[a-zA-Z0-9-.+]+);base64,', base64_string)
            if matches:
                mime_type = matches.group(1)
                
        extension = mime_type.split('/')[1]
        file_name = f"image.{extension}"
        
        return {
            "mimeType": mime_type,
            "fileName": file_name
        }
        
    async def upload_base64_image(self, base64_data, url):
        try:
            if 'data:image' in base64_data:
                image_buffer = base64_data.split(',')[1]
            else:
                image_buffer = base64_data
                
            image_info = self.get_image_type(base64_data)
            mime_type = image_info["mimeType"]
            file_name = image_info["fileName"]
            
            upload_data = {
                "rpc": "uploadFile",
                "req": {
                    "fileName": file_name,
                    "fileMimeType": mime_type,
                    "content": image_buffer
                }
            }
            
            logger.info("发送图片请求", "Server")
            
            token = token_manager.get_next_token_for_model(self.model)
            if not token:
                logger.error("没有可用的token", "Server")
                return ''
                
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                "Connection": "keep-alive",
                "Accept": "text/event-stream",
                "Content-Type": "text/plain;charset=UTF-8",
                "Cookie": token,
                "baggage": "sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c"
            }
            
            response = await Utils.run_in_executor(
                self.scraper.post,
                url, 
                headers=headers,
                data=json.dumps(upload_data),
            )
            
            if response.status_code != 200:
                logger.error(f"上传图片失败,状态码:{response.status_code},原因:{response.text}", "Server")
                return ''
                
            result = response.json()
            logger.info(f'上传图片成功: {result}', "Server")
            return result["fileMetadataId"]
            
        except Exception as error:
            logger.error(error, "Server")
            return ''
            
    async def prepare_chat_request(self, request_data):
        todo_messages = request_data["messages"]
        if request_data["model"] in ["grok-2-imageGen", "grok-3-imageGen", "grok-3-deepsearch"]:
            last_message = todo_messages[-1]
            if last_message["role"] != "user":
                raise ValueError("画图模型的最后一条消息必须是用户消息!")
            todo_messages = [last_message]
            
        file_attachments = []
        messages = ''
        last_role = None
        last_content = ''
        search = request_data["model"] in ["grok-2-search", "grok-3-search"]
        
        def remove_think_tags(text):
            import re
            text = re.sub(r'<think>[\s\S]*?<\/think>', '', text).strip()
            text = re.sub(r'!\[image\]\(data:.*?base64,.*?\)', '[图片]', text)
            return text
            
        async def process_image_url(content):
            if content["type"] == "image_url" and "data:image" in content["image_url"]["url"]:
                image_response = await self.upload_base64_image(
                    content["image_url"]["url"],
                    f"{CONFIG['API']['BASE_URL']}/api/rpc"
                )
                return image_response
            return None
            
        async def process_content(content):
            if isinstance(content, list):
                text_content = ''
                for item in content:
                    if item["type"] == "image_url":
                        text_content += ("[图片]" if text_content else '') + "\n" if text_content else "[图片]"
                    elif item["type"] == "text":
                        text_content += ("\n" + remove_think_tags(item["text"]) if text_content else remove_think_tags(item["text"]))
                return text_content
            elif isinstance(content, dict) and content is not None:
                if content["type"] == "image_url":
                    return "[图片]"
                elif content["type"] == "text":
                    return remove_think_tags(content["text"])
            return remove_think_tags(self.process_message_content(content))
            
        for current in todo_messages:
            role = "assistant" if current["role"] == "assistant" else "user"
            is_last_message = current == todo_messages[-1]
            
            logger.info(json.dumps(current, indent=2, ensure_ascii=False), "Server")
            if is_last_message and "content" in current:
                if isinstance(current["content"], list):
                    for item in current["content"]:
                        if item["type"] == "image_url":
                            logger.info("处理图片附件", "Server")
                            processed_image = await process_image_url(item)
                            if processed_image:
                                file_attachments.append(processed_image)
                elif isinstance(current["content"], dict) and current["content"].get("type") == "image_url":
                    processed_image = await process_image_url(current["content"])
                    if processed_image:
                        file_attachments.append(processed_image)
                        
            text_content = await process_content(current["content"])
            
            if text_content or (is_last_message and file_attachments):
                if role == last_role and text_content:
                    last_content += '\n' + text_content
                    messages = messages[:messages.rindex(f"{role.upper()}: ")] + f"{role.upper()}: {last_content}\n"
                else:
                    messages += f"{role.upper()}: {text_content or '[图片]'}\n"
                    last_content = text_content
                    last_role = role         
        return {
            "temporary": CONFIG["API"]["IS_TEMP_CONVERSATION"],
            "modelName": self.model_id,
            "message": messages.strip(),
            "fileAttachments": file_attachments[:4],
            "imageAttachments": [],
            "disableSearch": False,
            "enableImageGeneration": True,
            "returnImageBytes": False,
            "returnRawGrokInXaiRequest": False,
            "enableImageStreaming": False,
            "imageGenerationCount": 1,
            "forceConcise": False,
            "toolOverrides": {
                "imageGen": request_data["model"] in ["grok-2-imageGen", "grok-3-imageGen"],
                "webSearch": search,
                "xSearch": search,
                "xMediaSearch": search,
                "trendsSearch": search,
                "xPostAnalyze": search
            },
            "enableSideBySide": True,
            "isPreset": False,
            "sendFinalMetadata": True,
            "customInstructions": "",
            "deepsearchPreset": "default" if request_data["model"] == "grok-3-deepsearch" else "",
            "isReasoning": request_data["model"] == "grok-3-reasoning"
        }

class MessageProcessor:
    @staticmethod
    def create_chat_response(message, model, is_stream=False):
        base_response = {
            "id": f"chatcmpl-{str(uuid.uuid4())}",
            "created": int(datetime.now().timestamp()),
            "model": model
        }
        
        if is_stream:
            return {
                **base_response,
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "content": message
                    }
                }]
            }
        
        return {
            **base_response,
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": message
                },
                "finish_reason": "stop"
            }],
            "usage": None
        }

async def process_model_response(response, model):
    result = {"token": None, "imageUrl": None}
    
    if CONFIG["IS_IMG_GEN"]:
        if response and response.get("cachedImageGenerationResponse") and not CONFIG["IS_IMG_GEN2"]:
            result["imageUrl"] = response["cachedImageGenerationResponse"]["imageUrl"]
        return result
    
    if model == "grok-2":
        result["token"] = response.get("token")
    elif model in ["grok-2-search", "grok-3-search"]:
        if response and response.get("webSearchResults") and CONFIG["ISSHOW_SEARCH_RESULTS"]:
            result["token"] = f"\r\n<think>{await Utils.organize_search_results(response['webSearchResults'])}</think>\r\n"
        else:
            result["token"] = response.get("token")
    elif model == "grok-3":
        result["token"] = response.get("token")
    elif model == "grok-3-deepsearch":
        if response and response.get("messageTag") == "final":
            result["token"] = response.get("token")        
    elif model == "grok-3-reasoning":
        if response and response.get("isThinking", False) and not CONFIG["SHOW_THINKING"]:
            return result
            
        if response and response.get("isThinking", False) and not CONFIG["IS_THINKING"]:
            result["token"] = "<think>" + response.get("token", "")
            CONFIG["IS_THINKING"] = True
        elif response and not response.get("isThinking", True) and CONFIG["IS_THINKING"]:
            result["token"] = "</think>" + response.get("token", "")
            CONFIG["IS_THINKING"] = False
        else:
            result["token"] = response.get("token")
            
    return result

async def stream_response_generator(response, model):
    try:
        CONFIG["IS_THINKING"] = False
        CONFIG["IS_IMG_GEN"] = False
        CONFIG["IS_IMG_GEN2"] = False
        logger.info("开始处理流式响应", "Server")
        
        async def iter_lines():
            line_iter = response.iter_lines()
            while True:
                try:
                    line = await Utils.run_in_executor(lambda: next(line_iter, None))
                    if line is None: 
                        break
                    yield line
                except StopIteration:
                    break
                except Exception as e:
                    logger.error(f"迭代行时出错: {str(e)}", "Server")
                    break
        
        async for line in iter_lines():
            if not line:
                continue
                
            try:
                try:
                    line_str = line.decode('utf-8', errors='replace')
                    # 添加检查，确保解码后的字符串是有效的JSON格式
                    if not line_str.strip() or not line_str.strip()[0] in ['{', '[']:
                        logger.warning(f"无效的JSON数据: {line_str}", "Server")
                        continue
                except UnicodeDecodeError:
                    logger.warning("解码失败，跳过此行数据", "Server")
                    continue
                
                try:
                    line_json = json.loads(line_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON解析失败: {e}, 数据: {line_str[:50]}...", "Server")
                    continue
                
                if line_json and line_json.get("error"):
                    raise ValueError("RateLimitError")
                    
                response_data = line_json.get("result", {}).get("response")
                if not response_data:
                    continue
                    
                if response_data.get("doImgGen") or response_data.get("imageAttachmentInfo"):
                    CONFIG["IS_IMG_GEN"] = True
                    
                result = await process_model_response(response_data, model)
                
                if result["token"]:
                    yield f"data: {json.dumps(MessageProcessor.create_chat_response(result['token'], model, True))}\n\n"
                    
                if result["imageUrl"]:
                    CONFIG["IS_IMG_GEN2"] = True
                    data_image = await handle_image_response(result["imageUrl"], model)
                    yield f"data: {json.dumps(MessageProcessor.create_chat_response(data_image, model, True))}\n\n"
                    
            except Exception as error:
                logger.error(f"处理行数据错误: {str(error)}", "Server")
                continue
                
        yield "data: [DONE]\n\n"
        
    except Exception as error:
        logger.error(f"流式响应总体错误: {str(error)}", "Server")
        raise error

async def handle_normal_response(response, model):
    try:
        full_response = ''
        CONFIG["IS_THINKING"] = False
        CONFIG["IS_IMG_GEN"] = False
        CONFIG["IS_IMG_GEN2"] = False
        logger.info("开始处理非流式响应", "Server")
        image_url = None
        
        async def iter_lines():
            line_iter = response.iter_lines()
            while True:
                try:
                    line = await Utils.run_in_executor(lambda: next(line_iter, None))
                    if line is None:
                        break
                    yield line
                except StopIteration:
                    break
                except Exception as e:
                    logger.error(f"迭代行时出错: {str(e)}", "Server")
                    break
                    
        async for line in iter_lines():
            if not line:
                continue
                
            try:
                try:
                    line_str = line.decode('utf-8', errors='replace')
                    # 添加检查，确保解码后的字符串是有效的JSON格式
                    if not line_str.strip() or not line_str.strip()[0] in ['{', '[']:
                        logger.warning(f"无效的JSON数据: {line_str}", "Server")
                        continue
                except UnicodeDecodeError:
                    logger.warning("解码失败，跳过此行数据", "Server")
                    continue
                
                try:
                    line_json = json.loads(line_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON解析失败: {e}, 数据: {line_str[:50]}...", "Server")
                    continue
                
                if line_json and line_json.get("error"):
                    raise ValueError("RateLimitError")
                    
                response_data = line_json.get("result", {}).get("response")
                if not response_data:
                    continue
                    
                if response_data.get("doImgGen") or response_data.get("imageAttachmentInfo"):
                    CONFIG["IS_IMG_GEN"] = True
                    
                result = await process_model_response(response_data, model)
                
                if result["token"]:
                    full_response += result["token"]
                    
                if result["imageUrl"]:
                    CONFIG["IS_IMG_GEN2"] = True
                    image_url = result["imageUrl"]
                    
            except Exception as error:
                logger.error(f"处理行数据错误: {str(error)}", "Server")
                continue
                
        if CONFIG["IS_IMG_GEN2"] and image_url:
            data_image = await handle_image_response(image_url, model)
            return MessageProcessor.create_chat_response(data_image, model)
        else:
            return MessageProcessor.create_chat_response(full_response, model)
            
    except Exception as error:
        logger.error(f"非流式响应总体错误: {str(error)}", "Server")
        raise error

async def handle_image_response(image_url,model):
    MAX_RETRIES = 2
    retry_count = 0
    scraper = cloudscraper.create_scraper()
    
    while retry_count < MAX_RETRIES:
        try:
            token = token_manager.get_next_token_for_model(model)
            if not token:
                raise ValueError("没有可用的token")
                
            image_response = await Utils.run_in_executor(
                scraper.get,
                f"https://assets.grok.com/{image_url}",
                headers={
                    **CONFIG["DEFAULT_HEADERS"],
                    "cookie": token
                }
            )
            
            if image_response.status_code == 200:
                break
                
            retry_count += 1
            if retry_count == MAX_RETRIES:
                raise ValueError(f"上游服务请求失败! status: {image_response.status_code}")
                
            await asyncio.sleep(1 * retry_count)
            
        except Exception as error:
            logger.error(error, "Server")
            retry_count += 1
            if retry_count == MAX_RETRIES:
                raise error
                
            await asyncio.sleep(1 * retry_count)
    
    image_content = image_response.content
    
    if CONFIG["API"]["PICGO_KEY"]:
        form = aiohttp.FormData()
        form.add_field('source', 
                      io.BytesIO(image_content),
                      filename=f'image-{int(datetime.now().timestamp())}.jpg',
                      content_type='image/jpeg')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://www.picgo.net/api/1/upload",
                data=form,
                headers={"X-API-Key": CONFIG["API"]["PICGO_KEY"]}
            ) as response_url:
                if response_url.status != 200:
                    return "生图失败，请查看PICGO图床密钥是否设置正确"
                else:
                    logger.info("生图成功", "Server")
                    result = await response_url.json()
                    return f"![image]({result['image']['url']})"
    elif CONFIG["API"]["TUMY_KEY"]:
        form = aiohttp.FormData()
        form.add_field('file', 
                      io.BytesIO(image_content),
                      filename=f'image-{int(datetime.now().timestamp())}.jpg',
                      content_type='image/jpeg')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://tu.my/api/v1/upload",
                data=form,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {CONFIG['API']['TUMY_KEY']}"
                }
            ) as response_url:
                if response_url.status != 200:
                    return "生图失败，请查看TUMY图床密钥是否设置正确"
                else:
                    logger.info("生图成功", "Server")
                    result = await response_url.json()
                    return f"![image]({result['image']['url']})"
    # 如果没有PICGO_KEY或者TUMY_KEY则返回base64图片
    image_base64 = base64.b64encode(image_content).decode('utf-8')
    return f"![image](data:image/jpeg;base64,{image_base64})"


app = Quart(__name__)
app = cors(app, allow_origin="*", allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

@app.before_request
async def before_request():
    await logger.request_logger(request)

@app.route('/v1/models', methods=['GET'])
async def models():
    return jsonify({
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": int(datetime.now().timestamp()),
                "owned_by": "grok"
            } for model in CONFIG["MODELS"].keys()
        ]
    })


@app.route('/get/tokens', methods=['GET'])
async def get_tokens():
    auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if CONFIG["API"]["IS_CUSTOM_SSO"]:
        return jsonify({"error": '自定义的SSO令牌模式无法获取轮询sso令牌状态'}), 403
    elif auth_token != CONFIG["API"]["API_KEY"]:
        return jsonify({"error": 'Unauthorized'}), 401
        
    return jsonify(token_manager.get_token_status_map())

@app.route('/add/token', methods=['POST'])
async def add_token():
    auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if CONFIG["API"]["IS_CUSTOM_SSO"]:
        return jsonify({"error": '自定义的SSO令牌模式无法添加sso令牌'}), 403
    elif auth_token != CONFIG["API"]["API_KEY"]:
        return jsonify({"error": 'Unauthorized'}), 401
        
    try:
        data = await request.get_json()
        sso = data.get('sso')
        if not sso:
            return jsonify({"error": 'SSO令牌不能为空'}), 400
            
        await token_manager.add_token(f"sso-rw={sso};sso={sso}")
        return jsonify(token_manager.get_token_status_map().get(sso, {}))
    except Exception as error:
        logger.error(error, "Server")
        return jsonify({"error": '添加sso令牌失败'}), 500

@app.route('/delete/token', methods=['POST'])
async def delete_token():
    auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if CONFIG["API"]["IS_CUSTOM_SSO"]:
        return jsonify({"error": '自定义的SSO令牌模式无法删除sso令牌'}), 403
    elif auth_token != CONFIG["API"]["API_KEY"]:
        return jsonify({"error": 'Unauthorized'}), 401
        
    try:
        data = await request.get_json()
        sso = data.get('sso')
        if not sso:
            return jsonify({"error": 'SSO令牌不能为空'}), 400
            
        success = await token_manager.delete_token(f"sso-rw={sso};sso={sso}")
        if success:
            return jsonify({"message": '删除sso令牌成功'})
        else:
            return jsonify({"error": '删除sso令牌失败'}), 500
    except Exception as error:
        logger.error(error, "Server")
        return jsonify({"error": '删除sso令牌失败'}), 500

@app.route('/v1/chat/completions', methods=['POST'])
async def chat_completions():
    try:
        data = await request.get_json()
        auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')

        if auth_token:
            if CONFIG["API"]["IS_CUSTOM_SSO"]:
                await token_manager.set_token(f"sso-rw={auth_token};sso={auth_token}")
            elif auth_token != CONFIG["API"]["API_KEY"]:
                return jsonify({"error": "Unauthorized"}), 401
        else:
            return jsonify({"error": "Unauthorized"}), 401
                    
        model = data.get("model")
        stream = data.get("stream", False)
        retry_count = 0
        
        try:
            grok_client = GrokApiClient(model)
            request_payload = await grok_client.prepare_chat_request(data)
            
            while retry_count < CONFIG["RETRY"]["MAX_ATTEMPTS"]:
                retry_count += 1
                logger.info(f"开始请求(第{retry_count}次尝试)", "Server")
                
                token = token_manager.get_next_token_for_model(model)
                if not token:
                    logger.error(f"没有可用的{model}模型令牌", "Server")
                    if retry_count == CONFIG["RETRY"]["MAX_ATTEMPTS"]:
                        raise ValueError(f"没有可用的{model}模型令牌")
                    continue
                
                scraper = cloudscraper.create_scraper()
                
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                        "Connection": "keep-alive",
                        "Accept": "text/event-stream",
                        "Content-Type": "text/plain;charset=UTF-8",
                        "Cookie": token,
                        "baggage": "sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c"
                    }
                    logger.info(f"使用令牌: {token}", "Server")
                    
                    response = await Utils.run_in_executor(
                        scraper.post,
                        f"{CONFIG['API']['BASE_URL']}/rest/app-chat/conversations/new",
                        headers=headers,
                        data=json.dumps(request_payload),
                        stream=True
                    )
                    
                    if response.status_code == 200:
                        logger.info("请求成功", "Server")
                        
                        if stream:
                            return Response(
                                stream_response_generator(response, model),
                                content_type='text/event-stream',
                                headers={
                                    'Cache-Control': 'no-cache',
                                    'Connection': 'keep-alive'
                                }
                            )
                        else:
                            result = await handle_normal_response(response, model)
                            return jsonify(result)
                    else:
                        logger.error(f"请求失败: 状态码 {response.status_code}", "Server")
                        token_manager.remove_token_from_model(model, token)
                        
                except Exception as e:
                    logger.error(f"请求异常: {str(e)}", "Server")
                    token_manager.remove_token_from_model(model, token)
                    
            raise ValueError("请求失败，已达到最大重试次数")
            
        except Exception as e:
            logger.error(e, "ChatAPI")
            return jsonify({
                "error": {
                    "message": str(e),
                    "type": "server_error"
                }
            }), 500
            
    except Exception as e:
        logger.error(e, "ChatAPI")
        return jsonify({
            "error": {
                "message": str(e),
                "type": "server_error"
            }
        }), 500

@app.route('/', methods=['GET'])
async def index():
    return "api运行正常"

if __name__ == "__main__":
    asyncio.run(initialize_tokens())
    app.run(host="0.0.0.0", port=CONFIG["SERVER"]["PORT"])
