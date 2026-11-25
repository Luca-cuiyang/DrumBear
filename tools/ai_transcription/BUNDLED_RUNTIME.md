# Bundled AI transcription runtimes

These directories are intentionally ignored by Git because they add roughly
500 MB. Packaging expects them to exist locally:

- `audiveris/mac-arm64/Audiveris.app` — Audiveris 5.11.0 (Apple Silicon)
- `audiveris/win-x64/` — Audiveris 5.11.0 Windows x64 (`Audiveris.exe`, `app/`, `runtime/`)
- `python-win/` — embeddable Python 3.9.13 for Windows x64 with:
  - numpy 1.26.4
  - opencv-python-headless 4.10.0.84
  - Pillow 10.4.0
  - pypdfium2 4.30.0
- `tesseract/` — Tesseract OCR 5.x for Windows x64 (`tesseract.exe`, 依赖 DLL,
  `tessdata/eng.traineddata`)，用于识别图片上印刷的速度记号。

## Provisioning

1. Mount `Audiveris-5.11.0-macosx-arm64.dmg` and copy `Audiveris.app` to
   `audiveris/mac-arm64/`.
2. Extract `Audiveris-5.11.0-windows-x86_64.msi` (for example with
   `msiexec /a ... TARGETDIR=...`) and copy the `Audiveris/` contents to
   `audiveris/win-x64/`.
3. Create `python-win/` from `python-3.9.13-embed-amd64.zip`, add
   `python39._pth` entries for `python39.zip`, `.`, `..`, `Lib\site-packages`,
   `import site`（`..` 让脚本能导入同目录模块），then unpack the win_amd64
   wheels above into `Lib/site-packages`.
4. Copy a Tesseract Windows distribution into `tesseract/`（`tesseract.exe`、
   全部依赖 DLL、`tessdata/eng.traineddata`）。

`buildscripts/packaging/macOS/package.sh` and
`buildscripts/packaging/Windows/package_win.bat` verify these paths before
packaging.
