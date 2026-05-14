# Home Assistant 语音助手配置指南 (通义千问版)

配合您的 ESP32-S3 语音助手，请在 Home Assistant 中完成以下设置：

## 1. 安装 Extended OpenAI Conversation
这是连接通义千问最简便的方式。
- 在 **HACS** 中搜索并安装 `Extended OpenAI Conversation`。
- 如果没有 HACS，请手动将插件放入 `custom_components` 文件夹。

## 2. 配置 DashScope (通义千问)
1. 前往 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/) 获取 API Key。
2. 在 HA 中添加 `Extended OpenAI Conversation` 集成：
   - **Name**: `Qwen LLM`
   - **API Key**: `您的阿里云API密钥`
   - **Base URL**: `https://dashscope.aliyuncs.com/compatible-mode/v1`
   - **Model Name**: `qwen-turbo` (或 `qwen-max`)

## 3. 设置语音助手管道 (Assist Pipeline)
1. 进入 **设置 -> 语音助手**。
2. 点击 **添加助手**。
3. 配置管道参数：
   - **名称**: `通义千问助手`
   - **语言**: `中文 (简体)`
   - **对话提供者**: 选择 `Qwen LLM`。
   - **语音转文字 (STT)**: 选择 `Whisper` (推荐本地部署 `faster-whisper`)。
   - **文字转语音 (TTS)**: 选择 `Piper` (推荐) 或阿里云 TTS 插件。

## 4. 连接 ESP32 设备
1. 确保 ESP32 已烧录固件并联网。
2. 在 **设置 -> 设备与服务** 中，ESPHome 应该会自动发现 `esp32-s3-qwen-bot`。
3. 点击 **配置** 并输入代码（如有）。
4. 在设备页面中，将 **Voice Assistant Pipeline** 设置为刚才创建的 `通义千问助手`。

---
现在，您可以对着模块说 **“小管家”** 来唤醒它了！
