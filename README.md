
# grok2API 接入指南：基于 python 的实现

## 项目简介
本项目提供了一种简单、高效的方式通过 Docker 部署 使用openAI的格式转换调用grok官网，进行api处理。

>支持自动过cf屏蔽盾，需要自己ip没有被风控。如果被风控，将会升级为5秒盾，无法绕过。

## 如何检测ip是否被风控？
1. 打开无痕浏览器，输入https://grok.com
2. 直接进入则没有被风控，如果出现下图所示画面，则表示已经被风控，该ip无法使用本项目
   ![image](https://github.com/user-attachments/assets/0466aa57-9a31-4f7c-bd07-fece11f27646)
   
4. 如果风控后，过了5秒盾，会给与一个一年有效期的cf_clearance，可以将这个填入环境变量CF_CLEARANCE，这个cf_clearance和你的ip是绑定的，如果更换ip需要重新获取，可以提高破盾的稳定性（大概）。
5. 如果ip没有风控，不要加cf_clearance，加了可能反而因为校验问题出盾

### 功能特点
实现的功能：
1. 已支持文字生成图，使用grok-3-imageGen和grok-4-imageGen模型。
2. 已支持全部模型识图和传图，只会识别存储用户消息最新的一个图，历史记录图全部为占位符替代。
3. 已支持搜索功能，使用grok-3-search，可以选择是否关闭搜索结果
4. 已支持深度搜索功能，使用grok-3-deepsearch,grok-4-deepsearch，深度搜索支持think过程显示
5. 已支持推理模型功能，使用grok-3-reasoning
6. 已支持真流式，上面全部功能都可以在流式情况调用
7. 支持多账号轮询，在环境变量中配置
8. 可以选择是否移除思考模型的思考过程。
9. 支持自行设置轮询和负载均衡，而不依靠项目代码
10. 自动过CF屏蔽盾
11. 可自定义http和Socks5代理
12. 上下文40k时自动转换为文件以提高上下文限制
13. 已转换为openai格式。
14. 支持super会员账号token单独导入，暂不支持浏览器面板方式导入

## API 接口文档

### 模型管理
| 接口 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 模型列表 | GET | `/v1/models` | 获取可用模型列表 |
| 对话 | POST | `/v1/chat/completions` | 发起对话请求 |

### SSO令牌管理与安全设置
| 接口 | 方法 | 路径 | 请求体 | 描述 |
|------|------|------|--------|------|
| 添加SSO令牌 | POST | `/add/token` | `{sso: "eyXXXXXXXX"}` | 添加SSO认证令牌 |
| 删除SSO令牌 | POST | `/delete/token` | `{sso: "eyXXXXXXXX"}` | 删除SSO认证令牌 |
| 获取SSO令牌状态 | GET | `/get/tokens` | - | 查询所有SSO令牌状态 |
| 修改cf_clearance | POST | `/set/cf_clearance` | `{cf_clearance: "cf_clearance=XXXXXXXX"}` | 更新cf_clearance Cookie |

### TOKEN管理界面
使用如下接口：http://127.0.0.1:3000/manager

![image](https://github.com/user-attachments/assets/9caedf30-5075-4edb-b5c4-96852647a43d)


### 环境变量具体配置

|变量 | 说明 | 构建时是否必填 |示例|
|--- | --- | ---| ---|
|`MANAGER_SWITCH` | 是否开启管理界面 | （可以不填，默认是false） | `true/false`|
|`ADMINPASSWORD` | 管理界面的管理员密码，请区别于API_KEY，并且设置高强度密码 | （MANAGER_SWITCH没有开启时可以不填，默认是无） | `OjB6*BLlT&nV2M$x`|
|`IS_TEMP_CONVERSATION` | 是否开启临时会话，开启后会话历史记录不会保留在网页 | （可以不填，默认是false） | `true/false`|
|`CF_CLEARANCE` | cf的5秒盾后的值，随便一个号过盾后的都可以，这个cf_clearance和你的ip是绑定的，如果更换ip需要重新获取。通用，可以提高破盾的稳定性 | （可以不填，默认无） | `cf_clearance=xxxxxx`|
|`API_KEY` | 自定义认证鉴权密钥 | （可以不填，默认是sk-123456） | `sk-123456`|
|`PROXY` | 代理设置，支持https和Socks5 | 可不填，默认无 | -|
|`PICGO_KEY` | PicGo图床密钥，两个图床二选一 | 不填无法流式生图 | -|
|`TUMY_KEY` | TUMY图床密钥，两个图床二选一 | 不填无法流式生图 | -|
|`ISSHOW_SEARCH_RESULTS` | 是否显示搜索结果 | （可不填，默认关闭） | `true/false`|
|`SSO` | Grok官网SSO Cookie,可以设置多个使用英文 , 分隔，我的代码里会对不同账号的SSO自动轮询和均衡 | （除非开启IS_CUSTOM_SSO否则和SSO_SUPER二选一） | `sso,sso`|
|`SSO_SUPER` | Grok官网的会员账号的SSO Cookie,可以设置多个使用英文 , 分隔，我的代码里会对不同账号的SSO自动轮询和均衡 | （除非开启IS_CUSTOM_SSO否则否则和SSO二选一） | `sso,sso`|
|`PORT` | 服务部署端口 | （可不填，默认3000） | `3000`|
|`IS_CUSTOM_SSO` | 这是如果你想自己来自定义号池来轮询均衡，而不是通过我代码里已经内置的号池逻辑系统来为你轮询均衡启动的开关。开启后 API_KEY 需要设置为请求认证用的 sso cookie，同时SSO环境变量失效。一个apikey每次只能传入一个sso cookie 值，不支持一个请求里的apikey填入多个sso。想自动使用多个sso请关闭 IS_CUSTOM_SSO 这个环境变量，然后按照SSO环境变量要求在sso环境变量里填入多个sso，由我的代码里内置的号池系统来为你自动轮询 | （可不填，默认关闭） | `true/false`|
|`SHOW_THINKING` | 是否显示思考模型的思考过程 | （可不填，默认关闭） | `true/false`|

**注意事项**：
- 所有POST请求需要在请求体中携带相应的认证信息
- SSO令牌和cf_clearance是敏感信息，请妥善保管

## 方法一：Docker部署

### 1. 获取项目
克隆我的仓库：[grok2api](https://github.com/xLmiler/grok2api)
### 2. 部署选项

#### 方式A：直接使用Docker镜像
```bash
docker run -it -d --name grok2api_python \
  -p 3000:3000 \
  -v $(pwd)/data:/data \
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
    volumes:
      - ./data:/data
    environment:
      - API_KEY=your_api_key
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
  -v $(pwd)/data:/data \
  -e IS_TEMP_CONVERSATION=false \
  -e API_KEY=your_api_key \
  -e IS_CUSTOM_SSO=false \
  -e ISSHOW_SEARCH_RESULTS=false \
  -e PORT=3000 \
  -e SHOW_THINKING=true \
  -e SSO=your_sso \
  yourusername/grok2api:latest
```

## 方法二：Hugging Face部署

### 部署地址
[GrokPythonService](https://huggingface.co/spaces/yxmiler/GrokPythonService)

### 可用模型列表
- `grok-4`
- `grok-4-reasoning`
- `grok-4-imageGen`
- `grok-3`
- `grok-3-search`
- `grok-3-imageGen`
- `grok-3-deepsearch`
- `grok-3-deepersearch`
- `grok-3-reasoning`

### 模型可用次数参考
- grok-4所有模型 合计一共：30次  每3小时刷新 仅grok会员可用
- grok-3,grok-3-search,grok-3-imageGen 合计：20次  每3小时刷新
- grok-3-deepsearch：8次 每24小时刷新
- grok-3-deepersearch：3次 每24小时刷新
- grok-3-reasoning：10次 每24小时刷新

### cookie的获取办法：
1. 打开[grok官网](https://grok.com/)
2. 复制如下的SSO的cookie的值填入SSO变量即可
![9EA{{UY6 PU~PENQHYO5JS7](https://github.com/user-attachments/assets/539d4a53-9352-49fd-8657-e942a94f44e9)

### cf_clearance的获取办法：
1. 随便登录一个账号打开[grok官网](https://grok.com/)
2. 复制如下的cf_clearance的cookie的值填入CF_CLEARANCE变量即可，只需要填入一个，不可以多个,格式cf_clearance=xxxxx
![W1F8FTBT`~17(TFP5LS173Q](https://github.com/user-attachments/assets/f5603267-316a-4126-8c77-a84a91ee6344)


## 备注
- 消息基于用户的伪造连续对话
- 可能存在一定程度的降智
- 生图模型不支持历史对话，仅支持生图。
## 补充说明
- 如需使用流式生图的图像功能，需在[PicGo图床](https://www.picgo.net/)或者[tumy图床](https://tu.my/)申请API Key，前者似乎无法注册了，没有前面图床账号的可以选择后一个图床。
- 自动移除历史消息里的think过程，同时如果历史消息里包含里base64图片文本，而不是通过文件上传的方式上传，则自动转换为[图片]占用符。

## 注意事项
⚠️ 本项目仅供学习和研究目的，请遵守相关使用条款。

