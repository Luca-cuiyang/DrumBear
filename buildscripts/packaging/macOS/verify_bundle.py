#!/usr/bin/env python3

import os
import plistlib
import subprocess
import sys


SYSTEM_PREFIXES = (
    "/System/",
    "/usr/lib/",
    "/Library/Apple/",
)


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def is_macho(path):
    if not os.path.isfile(path) or os.path.islink(path):
        return False
    try:
        return "Mach-O" in run("file", "-b", path)
    except subprocess.CalledProcessError:
        return False


def dependencies(path):
    result = []
    lines = run("otool", "-L", path).splitlines()[1:]
    for line in lines:
        value = line.strip().split(" (", 1)[0]
        if value:
            result.append(value)
    return result


def install_name(path):
    output = run("otool", "-D", path).splitlines()
    return output[1].strip() if len(output) > 1 else None


def rpaths(path):
    result = []
    lines = run("otool", "-l", path).splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "cmd LC_RPATH":
            continue
        for detail in lines[index + 1:index + 4]:
            value = detail.strip()
            if value.startswith("path "):
                result.append(value[5:].split(" (offset ", 1)[0])
                break
    return result


def expand_prefix(value, executable_dir, loader_dir):
    value = value.replace("@executable_path", executable_dir)
    value = value.replace("@loader_path", loader_dir)
    return os.path.normpath(value)


def resolve_dependency(dependency, binary_path, executable_dir, search_rpaths):
    loader_dir = os.path.dirname(binary_path)
    candidates = []

    if dependency.startswith("@executable_path/"):
        candidates.append(expand_prefix(dependency, executable_dir, loader_dir))
    elif dependency.startswith("@loader_path/"):
        candidates.append(expand_prefix(dependency, executable_dir, loader_dir))
    elif dependency.startswith("@rpath/"):
        suffix = dependency[len("@rpath/"):]
        for rpath in search_rpaths:
            root = expand_prefix(rpath, executable_dir, loader_dir)
            candidates.append(os.path.normpath(os.path.join(root, suffix)))
        candidates.append(
            os.path.normpath(os.path.join(executable_dir, "..", "Frameworks", suffix))
        )
    else:
        candidates.append(dependency)

    candidates = list(dict.fromkeys(candidates))
    for candidate in candidates:
        if os.path.exists(candidate):
            return True, candidate

    return False, ", ".join(candidates) if candidates else dependency


def main():
    if len(sys.argv) != 2:
        print("Usage: verify_bundle.py <App.app>", file=sys.stderr)
        return 2

    app = os.path.abspath(sys.argv[1])
    contents = os.path.join(app, "Contents")
    executable_dir = os.path.join(contents, "MacOS")
    if not os.path.isdir(executable_dir):
        print(f"Invalid application bundle: {app}", file=sys.stderr)
        return 2

    search_roots = (
        executable_dir,
        os.path.join(contents, "Frameworks"),
        os.path.join(contents, "PlugIns"),
    )
    binaries = []
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for base, _, files in os.walk(root):
            for name in files:
                path = os.path.join(base, name)
                if is_macho(path):
                    binaries.append(path)

    if not binaries:
        print(f"No Mach-O binaries found in {app}", file=sys.stderr)
        return 2

    info_path = os.path.join(contents, "Info.plist")
    with open(info_path, "rb") as info_file:
        info = plistlib.load(info_file)
    main_executable = os.path.join(executable_dir, info["CFBundleExecutable"])

    executable_rpaths = []
    for path in binaries:
        if os.path.dirname(path) == executable_dir:
            executable_rpaths.extend(rpaths(path))
    main_rpaths = list(dict.fromkeys(executable_rpaths))
    errors = []

    for binary in binaries:
        own_install_name = install_name(binary)
        local_rpaths = rpaths(binary)
        combined_rpaths = list(dict.fromkeys(local_rpaths + main_rpaths))
        for dependency in dependencies(binary):
            if dependency == own_install_name:
                continue
            if dependency.startswith(SYSTEM_PREFIXES):
                continue

            resolved, checked = resolve_dependency(
                dependency, binary, executable_dir, combined_rpaths
            )
            relative = os.path.relpath(binary, app)
            if not resolved:
                errors.append(
                    f"{relative}: unresolved {dependency} (tried {checked})"
                )
                continue

            absolute = os.path.abspath(checked)
            if dependency.startswith("/") and not absolute.startswith(app + os.sep):
                errors.append(f"{relative}: external dependency {dependency}")

    errors = list(dict.fromkeys(errors))
    if errors:
        print("Bundle dependency verification failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print(f"Bundle dependency verification passed: {len(binaries)} Mach-O files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
