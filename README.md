# QQFarmHelper 2.0

基于 OpenCV 模板匹配的 Windows 桌面自动化工具，用于 QQ 经典农场小程序的自动偷菜、自动务农。支持 Win10 / Win11。

## ✨ 功能特性

### 核心功能
- 自动识别并定位 QQ 经典农场窗口
- 自动打开好友列表，遍历拜访好友
- **一键偷菜优先**：进入好友农场先点一键偷菜，再处理高级作物
- **高级作物单独摘取**：对需要单独点击「可摘」标识的高级作物，采用 A+B+E 三层兜底检测
- **一键务农次数限制**：每天最多点击指定次数（默认35次），可配置
- **自动重启刷新**：每隔3分钟自动关闭并重开小程序，解决信息刷新延迟问题

### 智能识别
- 多尺度模板匹配，适配不同分辨率
- **双按钮位置判断**：根据务农按钮 x 坐标自动区分单按钮/双按钮模式
- **装饰星星排除**：自动识别并排除农场装饰图案中的星星，避免误点击
- 多主题/多背景适配（白天、夜晚、雨天等）
- 未知页面自动截图保存，便于调试

### 界面
- 农场主题深色 GUI（customtkinter）
- 实时统计：访问次数、摘取次数、今日务农（带进度条）、空地次数
- 运行日志实时输出
- 开始/暂停/退出一键控制

## 🚀 使用方法

### 方式一：直接运行 exe（推荐）
1. 从 [Releases](https://github.com/Thecolt66/QQFarmHelper/releases) 下载最新版 `QQFarmHelper.exe`
2. 打开 QQ 经典农场小程序（窗口化即可，无需最大化）
3. 双击运行 `QQFarmHelper.exe`
4. 点击「开始运行」

### 方式二：源码运行
```bash
pip install -r requirements.txt
python main_gui.py
```

## ⚙️ 配置说明

配置文件 `config_runtime.json`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `refresh.interval_seconds` | 180 | 自动重启小程序间隔（秒） |
| `farm.daily_limit` | 35 | 每日一键务农最大次数 |
| `behavior.allow_fallback_click` | true | 模板未命中时是否使用兜底坐标 |
| `debug.save_unknown_screenshot` | true | 未知页面是否保存截图 |

## 🖼️ 模板说明

模板文件位于 `templates/` 目录，可自行裁剪替换：

| 模板文件 | 说明 |
|---------|------|
| `friend_menu.png` | 主界面右下角「好友」按钮 |
| `friend_tab.png` | 好友弹窗顶部标题栏 |
| `visit_button.png` | 好友列表中的绿色「拜访」按钮 |
| `home_button.png` | 好友农场右下角「回家」按钮 |
| `pick_button.png` | 底部「一键偷菜」按钮 |
| `pick_hand.png` | 偷菜手形图标（备用模板） |
| `farm_button.png` | 底部「一键务农」按钮 |
| `crop_pick_label.png` | 高级作物上方「可摘」文字标识 |
| `ready_star.png` | 作物成熟星星提示 |
| `deco_star_day.png` | 白天装饰星星（排除用，不点击） |
| `deco_star_night.png` | 夜晚装饰星星（排除用，不点击） |

## 📝 日志与截图

程序运行时会在同目录生成 `logs/` 文件夹：

### 日志文件
- `logs/gui_runtime_YYYY-MM-DD.log`：按日期命名的运行日志，**保留最近3天**，超过自动清理
- 同一天多次运行会追加到同一个日志文件

### 调试截图
- `logs/runtime_debug/unknown_YYYYMMDD_HHMMSS.png`：遇到未知页面时自动保存的截图
- **保留最近3天**，超过自动清理
- 可通过 `config_runtime.json` 中 `debug.save_unknown_screenshot: false` 关闭

### 务农次数统计
- `logs/farm_stats.json`：持久化保存今日务农次数，跨天自动重置
- 程序每次启动会读取已有次数，不会从0开始

## 📦 打包说明

使用 PyInstaller 打包为单文件 exe：

```bash
pip install pyinstaller
pyinstaller QQFarmHelper.spec --clean
```

产物位于 `dist/QQFarmHelper.exe`，单文件绿色版，双击即可运行。

## 🛠️ 环境要求

- Windows 10 / Windows 11
- Python 3.10+（源码运行时）
- 依赖：`pywin32`、`mss`、`opencv-python`、`numpy`、`customtkinter`

## ⚠️ 免责声明

本项目仅用于学习 Windows 桌面自动化、OpenCV 模板匹配和 Python 项目打包。使用者应自行遵守相关软件、游戏或平台的服务条款，使用风险由使用者自行承担。
