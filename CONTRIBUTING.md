# Contributing to USBBaiduSync

Thank you for your interest in contributing to USBBaiduSync! We welcome bug reports, feature requests, documentation improvements, and code contributions.

## 🛠️ Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/oneideals/usb-baidu-sync.git
   cd usb-baidu-sync
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller pytest pytest-cov
   ```

4. **Run the test suite:**
   ```bash
   pytest
   ```

5. **Run in Dry-Run mode (mock transfers):**
   ```bash
   python3 run.py --dry-run --verbose
   ```

## 📦 Building the Standalone App

To build the self-contained macOS `.app` bundle and distribution `.zip`:
```bash
./scripts/create_app.sh
```

## 🤝 Code Style & Standards

- Follow PEP 8 and use type hints where practical (`from __future__ import annotations`).
- Ensure all automated unit tests pass before submitting a Pull Request.
- Avoid introducing heavy dependencies; keep the footprint small and responsive.
- Respect macOS native UX conventions (status item, alerts, notifications).

## 📄 License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
