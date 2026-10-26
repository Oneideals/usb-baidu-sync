# USBBaiduSync 设计规范文档 (Design Spec)

- **项目名称**：USBBaiduSync (macOS U盘自动检测增量同步百度网盘工具)
- **文档版本**：1.0.0
- **创建日期**：2026-10-26
- **设计状态**：已评审 (Approved)

---

## 1. 业务目标与需求概述

### 1.1 核心目标
为 macOS 用户打造一款轻量级、免人工干预的常驻菜单栏工具。当外部 U 盘插入 Mac 时，系统自动感知并扫描其内容，比对本地历史指纹库，执行**增量上传**到用户指定的百度网盘目录。已上传过的历史文件无需再次上传，仅同步新加入或变动的文件。

### 1.2 关键特性与约束
1. **即插即检（零轮询）**：利用 macOS 原生 `NSWorkspace` 挂载通知，插拔毫秒级感知，不占用 CPU 资源。
2. **两级智能增量判定**：
   - 一级：`(相对路径, 文件大小, 修改时间)` 元数据秒级比对。
   - 二级：内容哈希校验（<10MB 完整 MD5，≥10MB 头部+尾部+大小指纹），防止假更新与重复传输。
3. **网盘归档组织策略**：
   - 基础目标路径可配置（例如：`/我的备份/U盘自动备份`）。
   - 按**插入日期 + U盘卷名**分目录归档，如 `<目标路径>/YYYY-MM-DD_<U盘名称>/<U盘内相对路径>`。
   - 若改天再次插入同一 U 盘，仅将新增或改动的文件归档至当天的日期子文件夹中。
4. **排除系统干扰文件**：自动过滤 macOS 隐藏与元数据文件（`.DS_Store`、`.Spotlight-V100`、`.Trashes`、`.fseventsd`、`._*` 等）。
5. **用户交互**：macOS 菜单栏（Status Bar）小图标常驻，支持查看同步状态/进度、一键配置网盘路径及 BDUSS 授权、手动触发及查看历史日志，关键节点推送 macOS 原生通知。

---

## 2. 整体架构与模块设计

系统划分为 5 个核心模块，架构如下图所示：

```
                    ┌───────────────────────────────┐
                    │     macOS 菜单栏应用 (rumps)   │
                    │   - 状态图标与动态文字展示    │
                    │   - 设置面板 / 查看日志 / 退出 │
                    └───────────────▲───────────────┘
                                    │ 事件通信 / 状态刷新
┌──────────────────────┐    ┌───────┴───────────────────────┐    ┌──────────────────────┐
│  macOS 系统通知中心   │◄───┤    中央协调器 (Coordinator)   ├───►│  本地指纹库 (SQLite)  │
│  - 挂载感知/同步完成 │    │    - 调度管理与任务状态分发   │    │  - 记录已上传文件指纹 │
└──────────────────────┘    └───────▲───────────────┬───────┘    └──────────────────────┘
                                    │               │
                    ┌───────────────┴────────┐      │ 触发增量传输队列
                    │  U 盘监听器 (Listener) │      ▼
                    │  - PyObjC 原生挂载监听 │  ┌──────────────────────┐
                    │  - 智能过滤系统盘与垃圾 │  │  BaiduPCS-Go 传输引擎 │
                    └────────────────────────┘  │  - 多线程切片增量上传 │
                                                └──────────────────────┘
```

### 2.1 模块职责说明

1. **`usb_listener.py` (U 盘监听器)**
   - 注册 Cocoa `NSWorkspaceDidMountNotification` 与 `NSWorkspaceDidUnmountNotification`。
   - 过滤系统启动盘（`/`）、只读镜像（DMG）、网络挂载卷（smb/afp）与 Time Machine 卷，仅保留可移动物理外部存储（如 FAT32、exFAT、NTFS、APFS 外部卷）。
   - 提取 U 盘卷名（Volume Name）与唯一硬件/文件系统标识（UUID）。

2. **`database.py` (本地 SQLite 存储)**
   - 存储路径：`~/Library/Application Support/USBBaiduSync/sync_records.db`。
   - 管理卷信息表 `usb_volumes` 与文件指纹表 `file_fingerprints`。
   - 提供增量比对查询、上传成功记录写入、断点重试状态标记接口。

3. **`baidu_engine.py` (BaiduPCS-Go 调度器)**
   - 管理 `BaiduPCS-Go` 可执行文件生命周期（自动检测并适配 macOS Apple Silicon / Intel 架构）。
   - 管理用户登录态（BDUSS），提供 `who()` 测试连通性接口。
   - 提供 `upload(local_path, remote_dir)` 接口，实时捕获标准输出解析上传进度与百分比。

4. **`coordinator.py` (中央协调器)**
   - 协调监听器、数据库、传输引擎与 UI。
   - 维护当前任务队列，控制并发，处理中途拔出 U 盘时的安全中断。
   - 派发状态通知至菜单栏与 macOS 系统通知中心。

5. **`app.py` / `menu_bar.py` (UI 与入口)**
   - 基于 `rumps` 构建 macOS 顶部状态栏应用。
   - 提供状态提示、设置窗口（目标目录、BDUSS 配置）、手动同步入口与日志浏览。

---

## 3. 数据结构与指纹算法

### 3.1 数据库 Schema (SQLite)

```sql
-- 1. U 盘卷信息表
CREATE TABLE IF NOT EXISTS usb_volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_uuid TEXT UNIQUE,          -- U 盘唯一标识 (如 diskutil 获取的 UUID，或卷名+总容量哈希兜底)
    volume_name TEXT NOT NULL,        -- U 盘显示名称 (如 KINGSTON)
    mount_path TEXT NOT NULL,         -- 当前挂载路径 (如 /Volumes/KINGSTON)
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP
);

-- 2. 文件指纹与上传历史表
CREATE TABLE IF NOT EXISTS file_fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_uuid TEXT NOT NULL,        -- 关联 U 盘 UUID
    rel_path TEXT NOT NULL,           -- 文件在 U 盘内的相对路径 (如 documents/work.xlsx)
    file_size INTEGER NOT NULL,       -- 文件大小 (字节)
    mtime REAL NOT NULL,              -- 最后修改时间戳
    fast_hash TEXT NOT NULL,          -- 快速计算的内容指纹 (MD5)
    remote_path TEXT NOT NULL,        -- 百度网盘完整存放路径
    upload_status TEXT NOT NULL,      -- 'SUCCESS', 'FAILED', 'INTERRUPTED'
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    UNIQUE(volume_uuid, rel_path)
);
CREATE INDEX IF NOT EXISTS idx_volume_rel ON file_fingerprints(volume_uuid, rel_path);
```

### 3.2 增量判定逻辑 (两级指纹算法)

对扫描到的每个文件 `f`：
```python
def should_upload(file_info, db_record):
    if not db_record or db_record['upload_status'] != 'SUCCESS':
        return True # 新文件或上次未成功，需要上传

    # 一级检查：大小和修改时间完全一致
    if file_info.size == db_record['file_size'] and abs(file_info.mtime - db_record['mtime']) < 1.0:
        return False # 0 耗时跳过

    # 二级检查：计算哈希比对
    current_hash = calculate_fast_hash(file_info.path, file_info.size)
    if current_hash == db_record['fast_hash']:
        # 内容未变，仅更新数据库里的 mtime
        update_record_mtime(db_record['id'], file_info.mtime)
        return False

    return True # 内容已变动，需要增量上传
```

**Fast Hash 策略**：
- 文件大小 `< 10MB`：计算完整 MD5。
- 文件大小 `≥ 10MB`：读取文件前 64KB + 中间 64KB + 尾部 64KB + 文件大小拼接求 MD5。数 GB 的大文件亦可在 5ms 内判定指纹。

---

## 4. 百度网盘目录生成与归档规则

- 用户在配置中指定网盘根基准目录（默认为 `/我的备份/U盘自动备份`）。
- 每次插入 U 盘触发同步时：
  1. 获取当前插入日期：`current_date = YYYY-MM-DD`（如 `2026-10-26`）。
  2. 获取 U 盘卷标：`volume_name = "KINGSTON"`。
  3. 计算该次归档的目标根目录：
     `session_remote_dir = f"{base_remote_dir}/{current_date}_{volume_name}"`
  4. 待上传文件的远端完整路径为：
     `remote_file_path = f"{session_remote_dir}/{file_rel_path}"`
- **增量归档特性**：
  - 只有**真正需要上传的文件**才会在当天日期目录下创建并上传。
  - 已在历史插入中上传过的文件不会重复上传，也不会在网盘创建空目录。

---

## 5. 异常处理与边界保障

1. **U 盘意外拔出 (Abrupt Unmount)**：
   - 监听 `NSWorkspaceDidUnmountNotification`。
   - 若正在传输的卷被卸载，立即向 `BaiduPCS-Go` 发送 `SIGTERM`，关闭文件读取句柄。
   - 将当前未完成的文件在 SQLite 中标记为 `INTERRUPTED`，下次插入时继续补传。
2. **百度网盘登录态过期 (401 / Invalid BDUSS)**：
   - `BaiduPCS-Go` 执行失败时自动识别登录态失效错误码。
   - 菜单栏图标立即置为 `⚠️` 警告状态，弹出 macOS 提示：“百度网盘登录已过期，请在设置中更新 BDUSS”。
3. **网络抖动与上传重试**：
   - 单个文件失败自动进行指数退避重试（最多 3 次）。
   - 若重试 3 次仍然失败，记录错误日志，标记为 `FAILED`，继续传输队列中后续文件，不阻塞整体进程。
4. **排除规则默认黑名单**：
   - 目录：`__MACOSX`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `System Volume Information`, `$RECYCLE.BIN`, `.TemporaryItems`
   - 文件：`.DS_Store`, `._*`, `Thumbs.db`, `desktop.ini`

---

## 6. 测试与验证方案

1. **单元测试 (`tests/test_incremental.py`)**：
   - 测试数据库初始化、记录写入与增量比对状态机。
   - 测试 Fast Hash 算法在大文件、小文件、空文件上的正确性与幂等性。
   - 测试忽略规则（Ignore Matcher）对 macOS 各种元数据文件的过滤。
2. **挂载事件模拟测试 (`tests/test_listener.py`)**：
   - 模拟模拟插入与卸载事件派发，验证 Coordinator 调度流水线。
3. **Dry-Run 模式测试**：
   - 引入 `--dry-run` 开关：插入 U 盘后，完整执行扫描、指纹比对与网盘路径生成，但仅打印拟上传清单，不发起真实网络传输。便于用户与测试人员快速校验。

---

## 7. 规格自审清单 (Self-Review Checklist)

- [x] **无占位符与未定项**：无任何 "TBD"、"TODO" 或模糊要求。
- [x] **逻辑一致性**：U 盘挂载识别、两级指纹比对、日期目录归档规则与 UI 交互前后一致。
- [x] **单次实施范围收敛**：结构清晰分为监听层、存储层、传输层与 UI 层，完全契合单一实施计划。
- [x] **歧义消除**：明确了当天多次插入与跨天插入时的归档目录组织规则，消除了增量目录歧义。
