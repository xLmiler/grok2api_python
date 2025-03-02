
# grok2API 接入指南：基于 Docker 的实现

## 项目简介
本项目提供了一种简单、高效的方式通过 Docker 部署 使用openAI的格式转换调用grok官网，进行api处理。

>原版nodej版本已失效，现在已重构为python，支持自动过cf屏蔽盾，需要自己ip没有被屏蔽。

## 方法一：Docker部署

### 1. 获取项目
克隆我的仓库：[grok2api](https://github.com/xLmiler/grok2api)
### 2. 部署选项

#### 方式A：直接使用Docker镜像
```bash
docker run -it -d --name grok2api_python \
  -p 3000:3000 \
  -e IS_TEMP_CONVERSATION=false \
  -e API_KEY=your_api_key \
  -e TUMY_KEY=你的图床key,和PICGO_KEY 二选一 \
  -e PICGO_KEY=你的图床key,和TUMY_KEY二选一 \
  -e IS_CUSTOM_SSO=false \
  -e ISSHOW_SEARCH_RESULTS=false \
  -e PORT=3000 \
  -e SHOW_THINKING=true \
  -e SSO=your_sso \
  yxmiler/grok2api_python:latest
```

#### 方式B：使用Docker Compose
````artifact
version: '3.8'
services:
  grok2api_python:
    image: yxmiler/grok2api_python:latest
    container_name: grok2api_python
    ports:
      - "3000:3000"
    environment:
      - API_KEY=your_api_key
      - TUMY_KEY=你的图床key,和PICGO_KEY 二选一
      - PICGO_KEY=你的图床key,和TUMY_KEY二选一
      - IS_TEMP_CONVERSATION=true
      - IS_CUSTOM_SSO=false
      - ISSHOW_SEARCH_RESULTS=false
      - PORT=3000
      - SHOW_THINKING=true
      - SSO=your_sso
    restart: unless-stopped
````

#### 方式C：自行构建
1. 克隆仓库
2. 构建镜像
```bash
docker build -t yourusername/grok2api .
```
3. 运行容器
```bash
docker run -it -d --name grok2api \
  -p 3000:3000 \
  -e IS_TEMP_CONVERSATION=false \
  -e API_KEY=your_api_key \
  -e TUMY_KEY=你的图床key,和PICGO_KEY 二选一 \
  -e PICGO_KEY=你的图床key,和TUMY_KEY二选一 \
  -e IS_CUSTOM_SSO=false \
  -e ISSHOW_SEARCH_RESULTS=false \
  -e PORT=3000 \
  -e SHOW_THINKING=true \
  -e SSO=your_sso \
  yourusername/grok2api:latest
```

### 3. 环境变量配置

|变量 | 说明 | 构建时是否必填 |示例|
|--- | --- | ---| ---|
|`IS_TEMP_CONVERSATION` | 是否开启临时会话，开启后会话历史记录不会保留在网页 | （可以不填，默认是false） | `true/false`|
|`API_KEY` | 自定义认证鉴权密钥 | （可以不填，默认是sk-123456） | `sk-123456`|
|`PICGO_KEY` | PicGo图床密钥，两个图床二选一 | 不填无法流式生图 | -|
|`TUMY_KEY` | TUMY图床密钥，两个图床二选一 | 不填无法流式生图 | -|
|`ISSHOW_SEARCH_RESULTS` | 是否显示搜索结果 | （可不填，默认关闭） | `true/false`|
|`SSO` | Grok官网SSO Cookie,可以设置多个使用英文 , 分隔，我的代码里会对不同账号的SSO自动轮询和均衡 | （除非开启IS_CUSTOM_SSO否则必填） | `sso,sso`|
|`PORT` | 服务部署端口 | （可不填，默认3000） | `3000`|
|`IS_CUSTOM_SSO` | 这是如果你想自己来自定义号池来轮询均衡，而不是通过我代码里已经内置的号池逻辑系统来为你轮询均衡启动的开关。开启后 API_KEY 需要设置为请求认证用的 sso cookie，同时SSO环境变量失效。一个apikey每次只能传入一个sso cookie 值，不支持一个请求里的apikey填入多个sso。想自动使用多个sso请关闭 IS_CUSTOM_SSO 这个环境变量，然后按照SSO环境变量要求在sso环境变量里填入多个sso，由我的代码里内置的号池系统来为你自动轮询 | （可不填，默认关闭） | `true/false`|
|`SHOW_THINKING` | 是否显示思考模型的思考过程 | （可不填，默认关闭） | `true/false`|

### 功能特点
实现的功能：
1. 已支持文字生成图，使用grok-2-imageGen和grok-3-imageGen模型。
2. 已支持全部模型识图和传图，只会识别存储用户消息最新的一个图，历史记录图全部为占位符替代。
3. 已支持搜索功能，使用grok-2-search或者grok-3-search模型，可以选择是否关闭搜索结果
4. 已支持深度搜索功能，使用grok-3-deepsearch
5. 已支持推理模型功能，使用grok-3-reasoning
6. 已支持真流式，上面全部功能都可以在流式情况调用
7. 支持多账号轮询，在环境变量中配置
8. 可以选择是否移除思考模型的思考过程。
9. 支持自行设置轮询和负载均衡，而不依靠项目代码
10. 自动过CF屏蔽盾
11. 已转换为openai格式。

### 可用模型列表
- `grok-2`
- `grok-2-imageGen`
- `grok-2-search`
- `grok-3`
- `grok-3-search`
- `grok-3-imageGen`
- `grok-3-deepsearch`
- `grok-3-reasoning`

### 模型可用次数参考
- grok-2,grok-2-imageGen,grok-2-search 合计：30次  每1小时刷新
- grok-3,grok-3-search,grok-3-imageGen 合计：20次  每2小时刷新
- grok-3-deepsearch：10次 每24小时刷新
- grok-3-reasoning：10次 每24小时刷新

### cookie的获取办法：
1. 打开[grok官网](https://grok.com/)
2. 复制如下的SSO的cookie的值填入SSO变量即可
![9EA{{UY6 PU~PENQHYO5JS7](https://github.com/user-attachments/assets/539d4a53-9352-49fd-8657-e942a94f44e9)



### API调用

#### Docker版本
- 模型列表：`/v1/models`
- 对话：`/v1/chat/completions`

## 备注
- 消息基于用户的伪造连续对话
- 可能存在一定程度的降智
- 生图模型不支持历史对话，仅支持生图。
## 补充说明
- 如需使用流式生图的图像功能，需在[PicGo图床](https://www.picgo.net/)或者[tumy图床](https://tu.my/)申请API Key，前者似乎无法注册了，没有前面图床账号的可以选择后一个图床。
- 自动移除历史消息里的think过程，同时如果历史消息里包含里base64图片文本，而不是通过文件上传的方式上传，则自动转换为[图片]占用符。

## 注意事项
⚠️ 本项目仅供学习和研究目的，请遵守相关使用条款。

