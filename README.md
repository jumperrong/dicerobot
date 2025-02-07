# 骰子机器人系统

## 项目简介
骰子机器人是一个基于微信的多功能聊天机器人，集成了骰子投掷、牌堆抽卡、天气查询和AI聊天等功能。适用于桌面角色扮演游戏（TRPG）和日常聊天场景。

## 主要功能
### 🎲 骰子系统
- 支持复杂骰子表达式（如`2d20k1+3d6dl1`）
- 优势/劣势投掷
- 多面骰支持（d4/d6/d8/d10/d12/d20/d100）

### 🃏 牌堆系统
- 内置多种牌堆（108将、万象无常等）
- 支持自定义牌堆（JSON/TXT格式）
- 108将牌堆支持图片展示

### 🌤️ 天气服务
- 实时天气查询
- 72小时天气预报
- 灾害预警通知
- 生活指数（穿衣/运动/紫外线）

### 🤖 AI聊天
- 通义千问集成
- 多会话管理
- 群聊/私聊权限控制
- 定时消息推送

## 快速开始
1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 配置config.yaml：
   ```yaml
   ai:
     qwen:
       api_key: your_api_key
       app_id: your_app_id
   ```

3. 启动机器人：
   ```bash
   python main.py
   ```

## 配置说明
### 核心配置

```yaml
bot:
  name: 骰子机器人
  version: 1.1.0

ai:
  qwen:
    api_key: your_api_key
    app_id: your_app_id
    group_chat:
      enabled_rooms: 
        - "群聊ID1"
        - "群聊ID2"
```

### 牌堆配置
```yaml
decks:
  108bro: 108将.txt
  dmt: 万象无常.json
  injury: 侠界伤残.json
  wm: 狂野法术浪涌.json
```

## 使用示例
### 骰子指令
```
.r 2d20k1+3d6dl1
```

### 天气查询
```
.weather 北京 3d
```

### 抽卡指令
```
.draw dmt 2
```

### AI聊天
```
@机器人 今天天气如何？
```

## 开发指南
1. 添加新牌堆：
   - 在`decks`目录下添加JSON/TXT文件
   - 更新config.yaml中的decks配置

2. 扩展新功能：
   - 在`functions.py`中添加处理函数
   - 在`CommandHandler`中注册新命令

## 贡献指南
欢迎提交Pull Request，请遵循以下规范：
- 保持代码风格一致
- 添加必要的单元测试
- 更新相关文档

## 许可证
MIT License 
