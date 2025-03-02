import requests
import json
import time

# 服务器配置
API_URL = "http://0.0.0.0:3000/v1/chat/completions"  # 修改为使用0.0.0.0而非localhost
API_KEY = "sk-123456"  # 根据需要修改

def test_deepsearch():
    """测试grok-3-deepsearch模型的调用，检查思考过程输出"""
    
    # 构建请求
    data = {
        "model": "grok-3-deepsearch",
        "messages": [
            {
                "role": "user",
                "content": "解释量子计算的基本原理"
            }
        ],
        "stream": True
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    print("发送请求...")
    response = requests.post(API_URL, json=data, headers=headers, stream=True)
    
    if response.status_code != 200:
        print(f"错误: {response.status_code}")
        print(response.text)
        return
    
    thinking_content = ""
    final_content = ""
    is_thinking = False
    
    print("处理响应...")
    for line in response.iter_lines():
        if not line:
            continue
            
        line = line.decode('utf-8')
        if line.startswith("data: "):
            line = line[6:]  # 移除 "data: " 前缀
            if line == "[DONE]":
                break
                
            try:
                chunk = json.loads(line)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                
                if content:
                    if "<think>" in content and not is_thinking:
                        is_thinking = True
                        print("开始思考过程...")
                    elif "</think>" in content and is_thinking:
                        is_thinking = False
                        print("结束思考过程，输出最终结果...")
                    
                    if is_thinking:
                        thinking_content += content
                    else:
                        # 如果不在思考模式，或者遇到</think>后的内容
                        if "</think>" in content:
                            parts = content.split("</think>", 1)
                            if len(parts) > 1:
                                thinking_content += parts[0] + "</think>"
                                final_content += parts[1]
                        else:
                            final_content += content
                            
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                print(f"原始行: {line}")
    
    print("\n===== 思考内容 =====")
    print(thinking_content)
    print("\n===== 最终内容 =====")
    print(final_content)

if __name__ == "__main__":
    test_deepsearch()