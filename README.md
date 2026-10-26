# USBBaiduSync (macOS U盘自动增量备份至百度网盘)

专为 macOS 设计的免人工干预 U 盘备份小工具。当你将 U 盘插入 Mac 电脑时，软件自动感知、过滤系统垃圾文件，通过两级指纹（元数据 + 切片 Hash）秒级比对，将新增或修改的文件增量备份到百度网盘的指定日期文件夹中。

---

## ✨ 核心特性

- **即插即检（零轮询）**：基于 macOS Cocoa 原生 `NSWorkspace` 挂载事件，无需后台常驻死循环，毫秒级响应，0 CPU 占用。
- **两级智能增量判定**：
  - **一级比对**：`(相对路径, 文件大小, 修改时间)` 元数据比对，未变动文件 0 毫秒跳过。
  - **二级比对**：Fast Hash 切片哈希校验（<10MB 完整 MD5，≥10MB 前后切片特征），防止假修改与重复传输。
- **智能归档目录**：
  - 在网盘目标目录下按 `YYYY-MM-DD_<U盘名称>/` 自动归档。
  - 隔天或改天再次插入时，已上传文件直接跳过，仅将当天新增的文件归档到当天日期目录中。
- **macOS 菜单栏常驻**：
  - 顶部状态栏图标动态显示当前状态（🟢 监听中 / 🔄 正在上传 / ✅ 同步完成 / ⚠️ 异常提示）。
  - 支持在菜单中一键修改网盘存储目录、绑定百度网盘 BDUSS、切换测试模拟（Dry-run）模式。
- **安全与异常容错**：
  - 传输中途如果拔出 U 盘，立即安全终止传输，已中断文件记录状态，下次插入自动接续。
  - 上传开始与完成自动推送 macOS 原生横幅通知。

---

## 🚀 快速上手

### 1. 环境准备
确保你的 Mac 已安装 Python 3.9+。进入项目目录安装依赖：
```bash
pip install -r requirements.txt
```

### 2. 百度网盘上传引擎 (BaiduPCS-Go)
工具底层使用高效的 Go 传输引擎 `BaiduPCS-Go`。推荐通过 Homebrew 一键安装：
```bash
brew install baidupcs-go
```
*或从 [BaiduPCS-Go Releases](https://github.com/qjfoidnh/BaiduPCS-Go/releases) 下载 macOS 版本放入系统 PATH 或 `~/Library/Application Support/USBBaiduSync/bin/BaiduPCS-Go`。*

### 3. 获取并配置百度网盘 BDUSS
1. 在浏览器（Chrome/Safari）登录你的百度网盘网页版 [pan.baidu.com](https://pan.baidu.com)。
2. 按 F12 打开开发者工具 -> Application (应用) -> Cookies -> `https://pan.baidu.com`。
3. 找到名为 `BDUSS` 的 Cookie 项，复制其 Value 字符串。
4. 启动本软件后，在菜单栏点击 **「🔑 设置百度网盘凭证 (BDUSS)...」** 粘贴保存即可。

### 4. 运行软件
- **测试模式（Dry-Run 模式，不实际上传，仅模拟扫描和比对）：**
  ```bash
  python3 run.py --dry-run
  ```
- **正式运行：**
  ```bash
  python3 run.py
  ```

---

## 🛠️ 目录与持久化规范

- **配置文件**：`~/Library/Application Support/USBBaiduSync/config.json`
- **增量指纹库**：`~/Library/Application Support/USBBaiduSync/sync_records.db`
- **运行日志**：可在菜单栏点击「📜 打开数据与日志目录」直接在访达中查看。
