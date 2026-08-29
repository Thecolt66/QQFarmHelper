# QQFarmHelper 2.0

基于 OpenCV 模板匹配的 Windows 桌面自动化工具，用于 QQ 经典农场小程序的自动偷菜、自动务农。支持 Win10 / Win11。

---

## ⚠️ 已知问题与注意事项

> 以下为当前版本已知的小概率问题，均不影响程序整体运行，程序会定期自动重启小程序（默认每 3 分钟，可配置），确保点击循环持续进行。

### 已知小 Bug

1. **装扮星星误点击**：程序有小概率会点击农场装扮图案上的星星装饰（已加入排除模板，但不同装扮可能仍有遗漏）
2. **漏摘部分作物**：有小概率漏掉一些可摘的高级作物（模板匹配阈值权衡所致）
3. **好友遍历异常**：有小概率会跳过某些好友，或反复点击同一好友；属于去重缓存的边界情况，重启小程序后会自动恢复

### 使用须知

4. **桌面快捷方式**：使用时请务必在桌面创建 QQ 经典农场小程序的快捷方式，程序通过关闭并重开桌面快捷方式来实现自动刷新
5. **问题反馈**：如遇卡死或其他特殊 Bug，可将日志文件（`logs/` 目录）或截图发送至邮箱 **2272176595@qq.com**，我会尽快修复

---

## ✨ 功能特性

### 核心功能
- 自动识别并定位 QQ 经典农场窗口
- 自动打开好友列表，遍历拜访好友
- **一键偷菜优先**：进入好友农场先点一键偷菜，再处理高级作物
- **高级作物单独摘取**：对需要单独点击「可摘」标识的高级作物，采用 A+B+E 三层兜底检测
- **一键务农次数限制**：每天最多点击指定次数（默认 35 次），可配置
- **自动重启刷新**：每隔 3 分钟自动关闭并重开小程序，解决好友信息刷新延迟问题

### 智能识别
- 多尺度模板匹配，适配不同分辨率
- **双按钮位置判断**：根据务农按钮 x 坐标自动区分单按钮/双按钮模式
- **装饰星星排除**：自动识别并跳过农场装饰图案中的星星，减少误点击
- 多主题适配（白天、夜晚、雨天等不同背景）
- 未知页面自动截图保存，便于调试

### 界面
- 农场主题深色 GUI（customtkinter）
- 实时统计：访问次数、摘取次数、今日务农（带进度条）、空地次数
- 运行日志实时输出
- 开始 / 暂停 / 退出一键控制

---

## 🚀 快速开始

### 方式一：直接运行 exe（推荐）

1. 从 [Releases](https://github.com/Thecolt66/QQFarmHelper/releases) 下载最新版 `QQFarmHelper.exe`
2. 在桌面创建 QQ 经典农场小程序的快捷方式（右键小程序 → 发送到 → 桌面快捷方式）
3. 打开 QQ 经典农场小程序（窗口化即可，无需最大化）
4. 双击运行 `QQFarmHelper.exe`
5. 确认程序找到游戏窗口后，点击「开始运行」

### 方式二：源码运行

```bash
pip install -r requirements.txt
python main_gui.py
```

---

## 📁 运行后目录结构

程序运行后，会在 exe（或项目）同目录生成以下内容：

```
QQFarmHelper.exe          # 主程序
config_runtime.json       # 配置文件（可手动修改）
templates/                # 模板图片库
├── friend_menu.png       #   主界面「好友」按钮
├── friend_tab.png        #   好友弹窗顶部标题栏
├── visit_button.png      #   绿色「拜访」按钮
├── home_button.png       #   「回家」按钮
├── pick_button.png       #   「一键偷菜」按钮
├── pick_hand.png         #   偷菜手形图标（备用）
├── farm_button.png       #   「一键务农」按钮
├── crop_pick_label.png   #   高级作物「可摘」文字
├── ready_star.png        #   作物成熟星星提示
├── deco_star_day.png     #   白天装饰星星（排除用）
└── deco_star_night.png   #   夜晚装饰星星（排除用）
logs/                     # 运行日志与调试截图
├── gui_runtime_2026-08-28.log   #   按日期命名的运行日志
├── farm_stats.json               #   今日务农次数持久化
└── runtime_debug/                #   未知页面调试截图
    └── unknown_20260828_133329.png
```

---

## ⚙️ 配置说明

配置文件为 `config_runtime.json`，可直接用记事本打开修改，修改后重启程序生效。

| 配置路径 | 默认值 | 说明 |
|----------|--------|------|
| `refresh.enabled` | `true` | 是否启用自动重启小程序 |
| `refresh.interval_seconds` | `180` | 自动重启间隔（秒），180 = 3 分钟 |
| `refresh.desktop_shortcut_name` | `"QQ经典农场"` | 桌面快捷方式名称，需与实际一致 |
| `farm.enabled` | `true` | 是否启用一键务农 |
| `farm.daily_limit` | `35` | 每日一键务农最大次数 |
| `farm.stats_file` | `"logs/farm_stats.json"` | 务农次数统计文件路径 |
| `behavior.allow_fallback_click` | `true` | 模板未命中时是否使用兜底坐标点击 |
| `behavior.visited_cache_seconds` | `900` | 好友去重缓存时间（秒） |
| `behavior.all_visible_visited_action` | `"revisit_top"` | 全部好友访问完后的动作（`revisit_top`/`clear_cache`/`wait`） |
| `debug.save_unknown_screenshot` | `true` | 遇到未知页面时是否保存截图 |
| `debug.debug_dir` | `"logs/runtime_debug"` | 调试截图保存目录 |
| `window_keywords` | `["QQ经典农场", ...]` | 游戏窗口标题关键词列表 |

### 常用修改示例

- **改成 2 分钟重启**：`"interval_seconds": 120`
- **改成每天务农 50 次**：`"daily_limit": 50`
- **关闭未知页面截图**：`"save_unknown_screenshot": false`
- **关闭自动务农**：`"farm.enabled": false`

---

## 🖼️ 模板自定义

如果程序在你的电脑上识别不准，可以自行裁剪模板替换 `templates/` 目录下的对应图片：

1. 运行 `diagnose.py` 截取当前游戏画面
2. 用画图工具裁剪出对应的按钮/图标（尽量只截 UI 元素本身，不要包含背景）
3. 保存为同名文件覆盖原模板
4. 重新运行程序

**裁剪原则**：模板只截游戏 UI 元素（按钮、图标、文字），不要包含变化的农场背景，这样一次截图就能适配所有主题。

---

## 📝 日志与截图

### 运行日志
- 文件：`logs/gui_runtime_YYYY-MM-DD.log`
- 按日期命名，同一天多次运行会追加到同一文件
- **保留最近 3 天**，超过自动清理

### 调试截图
- 目录：`logs/runtime_debug/unknown_YYYYMMDD_HHMMSS.png`
- 遇到无法识别的页面时自动保存
- **保留最近 3 天**，超过自动清理
- 可通过配置 `debug.save_unknown_screenshot: false` 关闭

### 务农次数统计
- 文件：`logs/farm_stats.json`
- 持久化保存今日务农次数，程序每次启动会读取已有次数，不会从 0 开始
- 跨天（日期变化）自动重置次数为 0

---

## 🛠️ 源码运行与打包

### 环境要求
- Windows 10 / Windows 11
- Python 3.10+
- 依赖：`pywin32`、`mss`、`opencv-python`、`numpy`、`customtkinter`

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行
```bash
python main_gui.py
```

### 打包为 exe
```bash
pip install pyinstaller
pyinstaller QQFarmHelper.spec --clean
```
产物位于 `dist/QQFarmHelper.exe`，单文件绿色版。

### 调试工具
- `python diagnose.py`：诊断窗口、截图、模板加载、页面识别
- `python debug_match.py`：详细输出每个模板的匹配分数和位置

---

## ⚠️ 免责声明

本项目仅用于学习 Windows 桌面自动化、OpenCV 模板匹配和 Python 项目打包。使用者应自行遵守相关软件、游戏或平台的服务条款，使用风险由使用者自行承担。
