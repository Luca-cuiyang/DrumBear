#!/usr/bin/env python3
# 把 Homebrew 的 FFmpeg 动态库及其依赖一起打包进 app 的 Contents/Frameworks/ffmpeg，
# 并把 install name 改成 @loader_path 相对引用，保证在没装 Homebrew FFmpeg 的机器上也能导出 MP4。
import os
import shutil
import subprocess
import sys
from pathlib import Path


CORE_V7 = {
    'libavformat.61.dylib': 'libavformat.61.dylib',
    'libavcodec.61.dylib': 'libavcodec.61.dylib',
    'libavutil.59.dylib': 'libavutil.59.dylib',
    'libswscale.8.dylib': 'libswscale.8.dylib',
    'libswresample.5.dylib': 'libswresample.5.dylib',
}

CORE_V8 = {
    'libavformat.62.dylib': 'libavformat.62.dylib',
    'libavcodec.62.dylib': 'libavcodec.62.dylib',
    'libavutil.60.dylib': 'libavutil.60.dylib',
    'libswscale.9.dylib': 'libswscale.9.dylib',
    'libswresample.6.dylib': 'libswresample.6.dylib',
}


def lipo_architectures(path):
    out = subprocess.check_output(['lipo', '-archs', path]).decode().strip()
    return set(out.split())


def find_source_dir():
    project_dir = Path(__file__).resolve().parents[3]
    candidates = [
        os.environ.get('DBSCORE_FFMPEG_DIR', ''),
        str(project_dir.parent / 'Qt' / '6.10.2' / 'macos' / 'lib'),
        '/opt/homebrew/lib',
        '/usr/local/lib',
    ]

    # Prefer a universal FFmpeg set. The app bundle is universal, so packaging an
    # arm64-only FFmpeg directory would break MP4 export on Intel Macs.
    preferred_sets = [CORE_V7, CORE_V8]
    for core in preferred_sets:
        for candidate in candidates:
            if not candidate:
                continue
            source = Path(candidate)
            if not all((source / name).exists() for name in core):
                continue
            if all({'arm64', 'x86_64'} <= lipo_architectures(source / name) for name in core):
                return source, core
    return None, None


def get_deps(path):
    out = subprocess.check_output(['otool', '-L', path]).decode()
    deps = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        dep = line.split('(')[0].strip()
        if dep.startswith('/opt/homebrew') or dep.startswith('/usr/local'):
            deps.append(dep)
    return deps


def main(app_path):
    ffdir = os.path.join(app_path, 'Contents', 'Frameworks', 'ffmpeg')
    source_dir, core = find_source_dir()
    if source_dir is None:
        raise RuntimeError(
            'No universal FFmpeg libraries found. Expected a universal FFmpeg 7 or 8 set '
            'in the Qt SDK, DBSCORE_FFMPEG_DIR, or the Homebrew library directories.'
        )

    os.makedirs(ffdir, exist_ok=True)

    # 清理上次打包残留，避免只读文件导致覆盖失败
    for name in os.listdir(ffdir):
        if name.endswith('.dylib'):
            p = os.path.join(ffdir, name)
            os.chmod(p, 0o644)
            os.remove(p)

    bundled = {}
    for plain, source_name in core.items():
        real = os.path.realpath(source_dir / source_name)
        shutil.copy2(real, os.path.join(ffdir, plain))
        bundled[real] = plain

    queue = list(bundled.keys())
    while queue:
        p = queue.pop()
        for d in get_deps(p):
            real = os.path.realpath(d) if os.path.exists(d) else d
            if real in bundled:
                continue
            base = os.path.basename(real)
            shutil.copy2(real, os.path.join(ffdir, base))
            bundled[real] = base
            queue.append(real)

    for real, plain in bundled.items():
        dest = os.path.join(ffdir, plain)
        subprocess.run(['install_name_tool', '-id', f'@loader_path/{plain}', dest], check=True)

    for real, plain in bundled.items():
        dest = os.path.join(ffdir, plain)
        for d in get_deps(dest):
            dreal = os.path.realpath(d) if os.path.exists(d) else d
            if dreal in bundled:
                dep_plain = bundled[dreal]
                subprocess.run(['install_name_tool', '-change', d, f'@loader_path/{dep_plain}', dest], check=True)

    print(f'bundle_ffmpeg: bundled {len(bundled)} dylibs into {ffdir}')


if __name__ == '__main__':
    main(sys.argv[1])
