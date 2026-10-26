# USBBaiduSync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 macOS 菜单栏小工具，在插入外部 U 盘时自动感应，通过两级特征指纹进行增量比对，将新增或变动文件上传至百度网盘指定目录下的日期归档文件夹中。

**Architecture:** 采用分层解耦架构：系统监听层（PyObjC 监听 NSWorkspace 挂载事件）-> 过滤与扫描层（排除系统垃圾）-> 存储与比对层（SQLite 两级元数据与切片 Hash 指纹比对）-> 调度与传输层（BaiduPCS-Go 进程管理与断点续传）-> 菜单栏 UI 层（rumps 状态展示与配置）。

**Tech Stack:** Python 3.9+, PyObjC (Cocoa NSWorkspace), rumps, SQLite3, BaiduPCS-Go, pytest.

**Spec:** [docs/superpowers/specs/2026-10-26-usb-baidu-sync-design.md](file:///Users/jerrycheng/LocalStorage/Vibecoding/usb-baidu-sync/docs/superpowers/specs/2026-10-26-usb-baidu-sync-design.md)

## Global Constraints

- 仅支持 macOS 平台（Darwin 内核，兼容 Apple Silicon 与 Intel）。
- 绝不使用高 CPU 占用的轮询扫描，必须使用系统级的 `NSWorkspaceDidMountNotification`。
- 网盘归档格式必须严格遵循 `<base_dir>/YYYY-MM-DD_<volume_name>/<rel_path>`。
- 排除规则必须默认包含 `.DS_Store`、`._*`、`.Spotlight-V100`、`.Trashes`、`.fseventsd`、`__MACOSX`。
- 本地数据存储路径严格置于 `~/Library/Application Support/USBBaiduSync/` 与 `~/Library/Logs/USBBaiduSync/`。

## Review Focus

1. **U 盘拔出并发竞争**：上传大文件过程中用户突然拔出 U 盘，协调器必须捕获 unmount 事件立即 SIGTERM 子进程，将该文件标记为 INTERRUPTED，不造成程序崩溃或数据库死锁。
2. **大文件防卡死与快速哈希**：GB 级以上超大文件不得全量读取 MD5，必须采用前64KB+后64KB+大小的快速指纹方案，控制比对耗时在 10ms 内。
3. **文件名编码与特殊字符**：U 盘常见包含空格、中文字符、特殊符号（如括号、单引号）的文件名，子进程参数构造必须避免 shell 注入并正确转义。
4. **多 U 盘独立识别**：插入不同 U 盘时，必须以 Volume UUID 为主键隔离文件指纹，避免不同 U 盘由于相同文件名而误判跳过。
5. **网盘凭证失效**：BDUSS 过期或网络中断时，引擎需准确识别并向协调器反馈明确状态码，触发 UI 警告与系统通知，不得无限死循环重试。

---

### Task 1: 项目脚手架与配置管理模块 (Config & Scaffolding)

**Files:**
- Create: `usb_baidu_sync/__init__.py`
- Create: `usb_baidu_sync/config.py`
- Create: `requirements.txt`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: None
- Produces: `ConfigManager.get_config() -> AppConfig`, `ConfigManager.update_config(dict) -> None`

- [ ] **Step 1: Write the failing test for configuration loading and defaults**

```python
# tests/test_config.py
from pathlib import Path
from usb_baidu_sync.config import ConfigManager

def test_default_config_generated(tmp_path):
    config_file = tmp_path / "config.json"
    manager = ConfigManager(config_path=config_file)
    cfg = manager.load()
    assert cfg.remote_base_dir == "/我的备份/U盘自动备份"
    assert ".DS_Store" in cfg.ignore_patterns
    assert cfg.dry_run is False
    assert config_file.exists()

def test_config_update(tmp_path):
    config_file = tmp_path / "config.json"
    manager = ConfigManager(config_path=config_file)
    manager.update({"remote_base_dir": "/自定义目录", "bduss": "test_token"})
    cfg = manager.load()
    assert cfg.remote_base_dir == "/自定义目录"
    assert cfg.bduss == "test_token"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'usb_baidu_sync'`

- [ ] **Step 3: Implement `usb_baidu_sync/config.py` and `requirements.txt`**

实现 `AppConfig` 数据类与 `ConfigManager`，支持默认配置生成、JSON 读写与用户目录适配。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add usb_baidu_sync/__init__.py usb_baidu_sync/config.py requirements.txt tests/test_config.py
baton checkpoint --tool antigravity --summary "feat: add config manager and project scaffolding"
```

---

### Task 2: 过滤规则与快速指纹计算模块 (Ignore Rules & Fast Hash)

**Files:**
- Create: `usb_baidu_sync/ignore_rules.py`
- Create: `usb_baidu_sync/fingerprint.py`
- Test: `tests/test_ignore_rules.py`
- Test: `tests/test_fingerprint.py`

**Interfaces:**
- Consumes: `AppConfig.ignore_patterns`
- Produces: `is_ignored(rel_path: str, patterns: list[str]) -> bool`, `calculate_fast_hash(file_path: Path, file_size: int) -> str`

- [ ] **Step 1: Write the failing tests for ignore rules and fast hash**

```python
# tests/test_ignore_rules.py
from usb_baidu_sync.ignore_rules import is_ignored

def test_is_ignored_mac_metadata():
    assert is_ignored(".DS_Store") is True
    assert is_ignored("subfolder/._image.png") is True
    assert is_ignored(".Spotlight-V100/Store.db") is True
    assert is_ignored("photos/family.jpg") is False

# tests/test_fingerprint.py
from pathlib import Path
from usb_baidu_sync.fingerprint import calculate_fast_hash

def test_fast_hash_small_file(tmp_path):
    p = tmp_path / "small.txt"
    p.write_text("hello world")
    h1 = calculate_fast_hash(p, p.stat().st_size)
    h2 = calculate_fast_hash(p, p.stat().st_size)
    assert h1 == h2
    assert len(h1) == 32

def test_fast_hash_large_file(tmp_path):
    p = tmp_path / "large.bin"
    # 模拟 > 10MB 文件
    with open(p, "wb") as f:
        f.seek(11 * 1024 * 1024)
        f.write(b"end")
    h = calculate_fast_hash(p, p.stat().st_size)
    assert len(h) == 32
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ignore_rules.py tests/test_fingerprint.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `ignore_rules.py` and `fingerprint.py`**

- `ignore_rules.py`: 基于 `fnmatch` 匹配文件名或相对路径前缀。
- `fingerprint.py`: `< 10MB` 走完整 MD5；`>= 10MB` 走首部 64KB + 尾部 64KB + 文件大小拼接 MD5。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ignore_rules.py tests/test_fingerprint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add usb_baidu_sync/ignore_rules.py usb_baidu_sync/fingerprint.py tests/test_ignore_rules.py tests/test_fingerprint.py
baton checkpoint --tool antigravity --summary "feat: add ignore rules filter and fast fingerprint calculator"
```

---

### Task 3: 本地 SQLite 存储与两级增量判重引擎 (Database & Incremental Engine)

**Files:**
- Create: `usb_baidu_sync/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: `calculate_fast_hash`
- Produces: `SyncDatabase.get_volume_record(uuid)`, `SyncDatabase.evaluate_file(...) -> tuple[bool, str]`, `SyncDatabase.record_upload_success(...)`

- [ ] **Step 1: Write the failing tests for database and incremental evaluation**

```python
# tests/test_database.py
from pathlib import Path
from usb_baidu_sync.database import SyncDatabase

def test_database_init_and_evaluate(tmp_path):
    db_file = tmp_path / "sync_records.db"
    db = SyncDatabase(db_path=db_file)
    
    # 首次评测：新文件需上传
    test_file = tmp_path / "doc.txt"
    test_file.write_text("content v1")
    stat = test_file.stat()
    
    need_upload, reason = db.evaluate_file(
        volume_uuid="VOL-123",
        rel_path="doc.txt",
        file_path=test_file,
        size=stat.st_size,
        mtime=stat.st_mtime
    )
    assert need_upload is True
    assert reason == "NEW_FILE"
    
    # 模拟上传成功写入
    db.record_upload_success(
        volume_uuid="VOL-123",
        volume_name="KINGSTON",
        rel_path="doc.txt",
        file_size=stat.st_size,
        mtime=stat.st_mtime,
        fast_hash="fakehash1",
        remote_path="/remote/doc.txt"
    )
    
    # 再次评测：未变动则跳过
    need_upload2, reason2 = db.evaluate_file(
        volume_uuid="VOL-123",
        rel_path="doc.txt",
        file_path=test_file,
        size=stat.st_size,
        mtime=stat.st_mtime
    )
    assert need_upload2 is False
    assert reason2 == "METADATA_MATCH"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `usb_baidu_sync/database.py`**

实现 SQLite 建表、索引建立、事务管理、`evaluate_file` 两级比对、`record_upload_success` 与 `record_interrupted`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_database.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add usb_baidu_sync/database.py tests/test_database.py
baton checkpoint --tool antigravity --summary "feat: add sqlite incremental state engine"
```

---

### Task 4: 网盘归档路径生成器与 BaiduPCS-Go 调度器 (Path Resolver & Baidu Engine)

**Files:**
- Create: `usb_baidu_sync/path_resolver.py`
- Create: `usb_baidu_sync/baidu_engine.py`
- Test: `tests/test_path_resolver.py`
- Test: `tests/test_baidu_engine.py`

**Interfaces:**
- Consumes: `AppConfig`
- Produces: `resolve_remote_path(base_dir: str, volume_name: str, rel_path: str, date_str: str) -> str`, `BaiduEngine.check_login() -> bool`, `BaiduEngine.upload_file(local_path, remote_dir) -> bool`

- [ ] **Step 1: Write the failing tests for path resolver and baidu engine mock**

```python
# tests/test_path_resolver.py
from usb_baidu_sync.path_resolver import resolve_remote_path

def test_resolve_remote_path_structure():
    path = resolve_remote_path(
        base_dir="/我的备份/U盘自动备份",
        volume_name="KINGSTON",
        rel_path="photos/2026/trip.jpg",
        date_str="2026-10-26"
    )
    assert path == "/我的备份/U盘自动备份/2026-10-26_KINGSTON/photos/2026/trip.jpg"

# tests/test_baidu_engine.py
from usb_baidu_sync.baidu_engine import BaiduEngine

def test_baidu_engine_dry_run_mode(tmp_path):
    engine = BaiduEngine(binary_path="mock", dry_run=True)
    assert engine.check_login() is True
    res = engine.upload_file(tmp_path / "test.txt", "/remote/test.txt")
    assert res is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_path_resolver.py tests/test_baidu_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `path_resolver.py` and `baidu_engine.py`**

- `path_resolver.py`: 统一生成规范格式的远端路径，处理斜杠与编码。
- `baidu_engine.py`: 管理 `BaiduPCS-Go` 的子进程调用、参数组装、错误输出解析与 `--dry-run` 模式支持。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_path_resolver.py tests/test_baidu_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add usb_baidu_sync/path_resolver.py usb_baidu_sync/baidu_engine.py tests/test_path_resolver.py tests/test_baidu_engine.py
baton checkpoint --tool antigravity --summary "feat: add remote path resolver and baidu engine wrapper"
```

---

### Task 5: U 盘目录扫描器与系统挂载事件监听器 (USB Scanner & Listener)

**Files:**
- Create: `usb_baidu_sync/usb_scanner.py`
- Create: `usb_baidu_sync/usb_listener.py`
- Test: `tests/test_usb_scanner.py`

**Interfaces:**
- Consumes: `ignore_rules.is_ignored`
- Produces: `scan_volume(mount_path: Path, ignore_patterns: list) -> list[FileInfo]`, `USBListener(on_mount_cb, on_unmount_cb)`

- [ ] **Step 1: Write the failing tests for USB scanner**

```python
# tests/test_usb_scanner.py
from pathlib import Path
from usb_baidu_sync.usb_scanner import scan_volume

def test_scan_volume_filters_ignored(tmp_path):
    (tmp_path / "keep.txt").write_text("hello")
    (tmp_path / ".DS_Store").write_text("trash")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "report.docx").write_text("doc")
    
    files = scan_volume(tmp_path, ignore_patterns=[".DS_Store"])
    rel_paths = [f.rel_path for f in files]
    assert "keep.txt" in rel_paths
    assert "sub/report.docx" in rel_paths
    assert ".DS_Store" not in rel_paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_usb_scanner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `usb_scanner.py` and `usb_listener.py`**

- `usb_scanner.py`: 递归遍历目录并构造 `FileInfo`（含相对路径、绝对路径、文件大小、mtime）。
- `usb_listener.py`: 封装 `NSWorkspace` 的通知监听，通过 block/回调暴露 `on_mount(mount_path, volume_name)` 与 `on_unmount(mount_path)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_usb_scanner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add usb_baidu_sync/usb_scanner.py usb_baidu_sync/usb_listener.py tests/test_usb_scanner.py
baton checkpoint --tool antigravity --summary "feat: add usb scanner and mount event listener"
```

---

### Task 6: 中央调度器与异常安全控制 (Coordinator & Interruption Handler)

**Files:**
- Create: `usb_baidu_sync/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: All previous modules (Config, DB, Engine, Scanner)
- Produces: `SyncCoordinator.start()`, `SyncCoordinator.stop()`, `SyncCoordinator.sync_volume(mount_path, volume_name) -> SyncSummary`

- [ ] **Step 1: Write the failing tests for coordinator pipeline**

```python
# tests/test_coordinator.py
from pathlib import Path
from usb_baidu_sync.coordinator import SyncCoordinator
from usb_baidu_sync.config import AppConfig

def test_coordinator_sync_pipeline(tmp_path):
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    (usb_dir / "file1.txt").write_text("content 1")
    
    cfg = AppConfig(dry_run=True)
    db_file = tmp_path / "test.db"
    coord = SyncCoordinator(config=cfg, db_path=db_file)
    
    summary = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB")
    assert summary.total_scanned == 1
    assert summary.uploaded_count == 1
    assert summary.skipped_count == 0
    
    # 第二次触发：全部跳过
    summary2 = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB")
    assert summary2.total_scanned == 1
    assert summary2.uploaded_count == 0
    assert summary2.skipped_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `usb_baidu_sync/coordinator.py`**

串联扫描、增量比对、远端路径解析、分批上传、SQLite 记录写入与突然卸载安全终止。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_coordinator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add usb_baidu_sync/coordinator.py tests/test_coordinator.py
baton checkpoint --tool antigravity --summary "feat: add central sync coordinator"
```

---

### Task 7: 状态栏菜单 UI (rumps) 与启动入口 (Menu Bar & CLI Entry)

**Files:**
- Create: `usb_baidu_sync/menu_bar.py`
- Create: `run.py`
- Modify: `README.md`
- Test: `tests/test_menu_bar.py`

**Interfaces:**
- Consumes: `SyncCoordinator`
- Produces: 启动完整的 macOS 菜单栏应用

- [ ] **Step 1: Write test for menu bar state transitions**

```python
# tests/test_menu_bar.py
from usb_baidu_sync.menu_bar import USBBaiduSyncApp

def test_menu_bar_initial_state():
    app = USBBaiduSyncApp(dry_run=True)
    assert app.title == "💾"
    assert "监听就绪" in app.status_item.title
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_menu_bar.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `menu_bar.py` and `run.py`**

- `menu_bar.py`: 实现基于 `rumps.App` 的状态栏图标、动态进度文本更新、配置弹窗（修改 BDUSS 和目标路径）、手动触发同步与查看日志。
- `run.py`: 命令行启动入口，支持 `--dry-run` 调试参数。
- `README.md`: 编写使用说明（安装依赖、配置 BDUSS、开机自启指引）。

- [ ] **Step 4: Run all tests to verify everything passes**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add usb_baidu_sync/menu_bar.py run.py README.md tests/test_menu_bar.py
baton checkpoint --tool antigravity --summary "feat: add menu bar ui, app entry and documentation"
```
