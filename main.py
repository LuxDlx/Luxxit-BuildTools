import sys
import os
import shutil
import platform
import requests
import subprocess
import stat
from pathlib import Path

# Constants
SCRIPT_PATH = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
LUX_PATH = SCRIPT_PATH / ".luxxit"
JAVA_PATH = LUX_PATH / ".java"
INFO_FILE = LUX_PATH / ".info"
LUX_FOLDER = LUX_PATH / ".lux"
MAVEN_FOLDER = LUX_PATH / ".maven"
FERNFLOWER_FOLDER = LUX_PATH / ".fernflower"
FERNFLOWER_JAR = FERNFLOWER_FOLDER / "fernflower.jar"
LUXXIT_FOLDER = LUX_PATH / "Luxxit"

WIN_URL = "https://github.com/adoptium/temurin23-binaries/releases/download/jdk-23.0.2%2B7/OpenJDK23U-jdk_x64_windows_hotspot_23.0.2_7.zip"
LINUX_URL = "https://github.com/adoptium/temurin23-binaries/releases/download/jdk-23.0.2%2B7/OpenJDK23U-jdk_x64_linux_hotspot_23.0.2_7.tar.gz"
LUXDELUX_URL = "https://s3.amazonaws.com/sillysoft/LuxDelux-linux.tgz"
MAVEN_URL = "https://qwertz.app/downloads/LuxApp/apache-maven-3.9.11-bin.zip"
FERNFLOWER_URL = "https://qwertz.app/downloads/LuxApp/fernflower.jar"

# Helper for tqdm
def get_tqdm():
    try:
        from tqdm import tqdm
        return tqdm
    except ImportError:
        print("tqdm not installed. Install with: pip install tqdm")
        sys.exit(1)

# Permission fix for Windows
def on_rm_error(func, path, exc_info):
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise

def detect_os():
    if platform.system().lower().startswith("win"):
        return "windows"
    elif platform.system().lower().startswith("linux"):
        return "linux"
    else:
        raise Exception("Unsupported OS")

def clean_and_prepare_dirs():
    if LUX_PATH.exists():
        shutil.rmtree(LUX_PATH, onerror=on_rm_error)
    JAVA_PATH.mkdir(parents=True, exist_ok=True)
    LUX_FOLDER.mkdir(parents=True, exist_ok=True)
    MAVEN_FOLDER.mkdir(parents=True, exist_ok=True)
    FERNFLOWER_FOLDER.mkdir(parents=True, exist_ok=True)
    LUXXIT_FOLDER.mkdir(parents=True, exist_ok=True)

def write_info_file(os_name):
    with open(INFO_FILE, "w") as f:
        f.write(f"OS: {os_name}\n")

def download_file(url, dest, show_progress=False):
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    total = int(resp.headers.get('content-length', 0))
    tqdm = get_tqdm() if show_progress else None
    with open(dest, "wb") as f:
        if tqdm:
            for data in tqdm(resp.iter_content(1024*1024), total=total // (1024*1024) + 1, unit='MB', desc=f"Downloading {os.path.basename(dest)}"):
                f.write(data)
        else:
            for data in resp.iter_content(1024*1024):
                f.write(data)

def extract_file(archive_path, dest_dir, os_name=None):
    if archive_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(dest_dir)
    elif archive_path.suffix in [".gz", ".tgz"]:
        import tarfile
        with tarfile.open(archive_path, "r:gz") as tar_ref:
            tar_ref.extractall(dest_dir)
    else:
        raise Exception(f"Unknown archive format for {archive_path}")

def find_java_bin_dir(java_path, os_name):
    # Find the bin directory inside the extracted JDK
    for entry in os.scandir(java_path):
        if entry.is_dir():
            bin_dir = Path(entry.path) / "bin"
            if bin_dir.exists():
                return bin_dir
    raise Exception("Could not find Java bin directory")

def prepare_fernflower_and_luxcore():
    print("Downloading fernflower.jar...")
    download_file(FERNFLOWER_URL, FERNFLOWER_JAR, show_progress=True)
    # Move LuxCore.jar
    luxcore_src = LUX_FOLDER / "LuxDelux" / "LuxCore.jar"
    luxcore_dst = FERNFLOWER_FOLDER / "LuxCore.jar"
    if not luxcore_src.exists():
        raise Exception(f"{luxcore_src} does not exist!")
    shutil.copy2(luxcore_src, luxcore_dst)

def run_fernflower(java_bin_dir):
    os.makedirs(FERNFLOWER_FOLDER / "decompiled", exist_ok=True)
    fernflower_cmd = [
        str(java_bin_dir / "java"),
        "-jar",
        str(FERNFLOWER_JAR),
        str(FERNFLOWER_FOLDER / "LuxCore.jar"),
        str(FERNFLOWER_FOLDER / "decompiled")
    ]
    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_bin_dir.parent)
    env["PATH"] = str(java_bin_dir) + os.pathsep + env.get("PATH", "")
    print("Running Fernflower decompiler...")
    result = subprocess.run(fernflower_cmd, cwd=FERNFLOWER_FOLDER, env=env, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise Exception("Fernflower decompilation failed!")
    
def extract_jar_case_safe(jar_path, output_dir):
    import zipfile
    import os

    def fix_case_conflict(existing, name):
        # Only the first character can differ in case, rest is always lowercase
        if not existing:
            return name
        # Compare only first character case
        for exist_name in existing:
            if exist_name[1:] == name[1:] and exist_name[0].lower() == name[0].lower() and exist_name[0] != name[0]:
                # Conflict: only first char differs in case
                return name[0] + "_" + name[1:]
        return name

    with zipfile.ZipFile(jar_path, 'r') as jar:
        # Track directories/files at each level
        dir_contents = {}

        for file_info in jar.infolist():
            parts = file_info.filename.split('/')
            if not parts or parts == ['']:
                continue

            # Build up the path, fixing conflicts at each level
            curr_dir = output_dir
            for i, part in enumerate(parts):
                if not part:
                    continue
                parent = str(curr_dir)
                if parent not in dir_contents:
                    dir_contents[parent] = set()
                fixed_part = fix_case_conflict(dir_contents[parent], part)
                dir_contents[parent].add(fixed_part)
                curr_dir = os.path.join(curr_dir, fixed_part)
            target_path = curr_dir

            if file_info.is_dir():
                os.makedirs(target_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with jar.open(file_info) as src, open(target_path, 'wb') as dst:
                    dst.write(src.read())

def extract_decompiled_luxcore():
    print("Extracting decompiled LuxCore.jar with case-aware method...")
    LUXXIT_FOLDER.mkdir(parents=True, exist_ok=True)
    decompiled_jar = FERNFLOWER_FOLDER / "decompiled" / "LuxCore.jar"
    if not decompiled_jar.exists():
        raise Exception(f"{decompiled_jar} does not exist!")
    extract_jar_case_safe(decompiled_jar, LUXXIT_FOLDER)
    print("Extraction complete!")

def main_cli():
    os_name = detect_os()
    print(f"Detected OS: {os_name}")
    print("Cleaning and preparing directories...")
    clean_and_prepare_dirs()
    print("Writing info file...")
    write_info_file(os_name)
    print("Downloading Java runtime...")
    url = WIN_URL if os_name == "windows" else LINUX_URL
    archive_name = url.split("/")[-1]
    archive_path = JAVA_PATH / archive_name
    download_file(url, archive_path, show_progress=True)
    print("Extracting Java runtime...")
    extract_file(archive_path, JAVA_PATH, os_name)
    print("Cleaning up Java archive...")
    archive_path.unlink()
    print("Downloading LuxDelux...")
    lux_archive_name = LUXDELUX_URL.split("/")[-1]
    lux_archive_path = LUX_FOLDER / lux_archive_name
    download_file(LUXDELUX_URL, lux_archive_path, show_progress=True)
    print("Extracting LuxDelux...")
    extract_file(lux_archive_path, LUX_FOLDER)
    print("Cleaning up LuxDelux archive...")
    lux_archive_path.unlink()
    print("Downloading Maven...")
    maven_archive_name = MAVEN_URL.split("/")[-1]
    maven_archive_path = MAVEN_FOLDER / maven_archive_name
    download_file(MAVEN_URL, maven_archive_path, show_progress=True)
    print("Extracting Maven...")
    extract_file(maven_archive_path, MAVEN_FOLDER)
    print("Cleaning up Maven archive...")
    maven_archive_path.unlink()
    print("Preparing Fernflower and LuxCore.jar...")
    prepare_fernflower_and_luxcore()
    print("Locating Java bin directory...")
    java_bin_dir = find_java_bin_dir(JAVA_PATH, os_name)
    run_fernflower(java_bin_dir)
    print("Fernflower decompilation complete!")
    extract_decompiled_luxcore()
    thestuff()

def refactor_luxxit_structure(luxxit_dir):
    luxxit_dir = Path(luxxit_dir).resolve()
    src_java = luxxit_dir / "src" / "main" / "java"
    src_resources = luxxit_dir / "src" / "main" / "resources"
    lib_dir = luxxit_dir / "lib"
    src_java.mkdir(parents=True, exist_ok=True)
    src_resources.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(parents=True, exist_ok=True)

    # Move "com" directory
    com_dir = luxxit_dir / "com"
    if com_dir.exists() and com_dir.is_dir():
        shutil.move(str(com_dir), str(src_java / "com"))

    # Move "A" directory
    a_dir = luxxit_dir / "A"
    if a_dir.exists() and a_dir.is_dir():
        # Rename "A" to "random"
        a_dir = a_dir.rename(a_dir.with_name("random"))
        shutil.move(str(a_dir), str(src_java / "com" / "sillysoft" / "lux"))
    base_path = Path(str(src_java / "com" / "sillysoft" / "lux" / "random"))
    subdir = base_path / "A"
    if not subdir.exists() or not subdir.is_dir():
        print(f"Subdirectory {subdir} does not exist.")
        return

    # Move all files from subdir to base_path
    for item in subdir.iterdir():
        target = base_path / item.name
        if target.exists():
            print(f"Warning: {target} already exists. Skipping.")
            continue
        shutil.move(str(item), str(target))
        print(f"Moved {item} -> {target}")

    # Remove the subdir if now empty
    try:
        subdir.rmdir()
        print(f"Removed empty directory {subdir}")
    except OSError:
        print(f"Directory {subdir} is not empty, not removed.")
    # Delete META-INF directory
    meta_inf = luxxit_dir / "META-INF"
    if meta_inf.exists() and meta_inf.is_dir():
        shutil.rmtree(meta_inf)

    # Move resource files from root to resources
    for ext in [".png", ".html", ".properties", ".wav", ".jpg", ".gif", ".txt", ".ttf", ".jar"]:
        for file in luxxit_dir.glob(f"*{ext}"):
            shutil.move(str(file), str(src_resources / file.name))

    # Download exe4jlib.jar into lib
    exe4j_url = "https://qwertz.app/downloads/LuxApp/exe4jlib.jar"
    exe4j_dest = lib_dir / "exe4jlib.jar"
    if not exe4j_dest.exists():
        print(f"Downloading exe4jlib.jar to {exe4j_dest} ...")
        resp = requests.get(exe4j_url, stream=True)
        resp.raise_for_status()
        with open(exe4j_dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print("exe4jlib.jar downloaded.")
    else:
        print("exe4jlib.jar already exists.")
    print("Refactoring complete!")

def safe_rename(src, dst):
    print(src, dst)
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        print(f"Renamed {src} -> {dst}")     

def process_renames(luxxit_path, rename_file):
    base = Path(luxxit_path).resolve() / "src" / "main" / "java"
    with open(rename_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=>' not in line:
                print(f"Skipping invalid line: {line}")
                continue
            src_rel, dst_rel = [part.strip() for part in line.split('=>', 1)]
            src = base / src_rel
            dst = base / dst_rel
            safe_rename(src, dst)


def thestuff():
    
    refactor_luxxit_structure(".luxxit/Luxxit")
    process_renames(".luxxit/Luxxit", "renames.txt")
    import patching

    patching.apply_patch(".luxxit/Luxxit", "luxxit.patch")

    # build with maven
    if detect_os() == "windows":
        mvn = "mvn.cmd"
    else:
        subprocess.run(["chmod", "+x", str(LUX_PATH / ".maven" / "apache-maven-3.9.6" / "bin" / "mvn")])
        mvn = "mvn"
    command = [
        str(LUX_PATH / ".maven" / "apache-maven-3.9.6" / "bin" / mvn),
        "-f",
        str(LUX_PATH / "Luxxit" / "pom.xml"),
        "clean",
        "package",
        "-X",
        "-Dmaven.compiler.executable=./java/bin/javac"
    ]
    env = os.environ.copy()
    java_bin_dir = find_java_bin_dir(JAVA_PATH, detect_os())
    env["JAVA_HOME"] = str(java_bin_dir.parent)
    env["PATH"] = str(java_bin_dir) + os.pathsep + env.get("PATH", "")
    print("Running Fernflower decompiler...")
    try:
        subprocess.run(command, check=True, cwd=LUX_PATH / "Luxxit", env=env)
        print("Maven build completed successfully!")
    except subprocess.CalledProcessError as e:
        print("Maven build failed:", e)
        sys.exit(1)

    shutil.move(
        str(LUX_PATH / "Luxxit" / "target" / "LuxCore-1.0.jar"),
        str("Luxxit.jar")
    )
    shutil.move(str(LUX_PATH / ".java" / "jdk-23.0.2+7"), "java")
    shutil.move(str(LUX_PATH / ".lux" / "LuxDelux" / "Support"), "Support")

    with open("luxxit.cmd", "w", encoding="utf-8") as f:
        f.write(f'@rem LUXXIT SERVER STARTUP SCRIPT - WINDOWS\n"./java/bin/java" -Djava.awt.headless=true -cp * com.sillysoft.lux.Lux -headless -network=true -public=true -map=RomanEmpireII -cards=4e3 -conts=5 -time=30 -name={USERNAME} -desc=LuxxitPoweredServer! -regCode={REG_CODE}\n@rem Thanks for using Luxxit!\n@rem Made by QWERTZ')
        f.close()
    with open("luxxit.sh", "w", encoding="utf-8") as f:
        f.write(f'# LUXXIT SERVER STARTUP SCRIPT - LINUX\n"./java/bin/java" -Djava.awt.headless=true -cp "Luxxit.jar:lib/*" com.sillysoft.lux.Lux -headless -network=true -public=true -map=RomanEmpireII -cards=4e3 -conts=5 -time=30 -name={USERNAME} -desc=LuxxitPoweredServer! -regCode={REG_CODE}\n# Thanks for using Luxxit!\n# Made by QWERTZ')
        f.close()
    
    print("LUXXIT BUILD SUCCESS!")
    print("Instructions for your os:")
    if detect_os() == "windows":
        print("Run luxxit.cmd to start the server.")
    else:
        print("Run luxxit.sh to start the server. Make sure to run 'chmod +x luxxit.sh' first.")

if __name__ == "__main__":
    if "update" in sys.argv:
        print("Updating BuildTools...")
        download_file("https://raw.githubusercontent.com/LuxDlx/Luxxit-BuildTools/refs/heads/master/renames.txt", "renames.txt", show_progress=True)
        download_file("https://raw.githubusercontent.com/LuxDlx/Luxxit-BuildTools/refs/heads/master/main.py", "main.py", show_progress=True)
        download_file("https://raw.githubusercontent.com/LuxDlx/Luxxit-BuildTools/refs/heads/master/patching.py", "patching.py", show_progress=True)
        download_file("https://raw.githubusercontent.com/LuxDlx/Luxxit-BuildTools/refs/heads/master/luxxit.patch", "luxxit.patch", show_progress=True)
        sys.exit(0)
    if "clean" in sys.argv:
        if LUX_PATH.exists():
            shutil.rmtree(LUX_PATH, onerror=on_rm_error)
        print("Cleaned up Luxxit directories.")
        try:
            shutil.rmtree("plugins", onerror=on_rm_error)
        except:
            pass
        try:
            shutil.rmtree("Support", onerror=on_rm_error)
        except:
            pass
        try:
            shutil.rmtree("java", onerror=on_rm_error)
        except:
            pass
        try:
            os.remove("Luxxit.jar")
        except:
            pass
        try:
            os.remove("luxxit.cmd")
        except:
            pass
        try:
            os.remove("luxxit.sh")
        except:
            pass
        try:
            shutil.rmtree("__pycache__", onerror=on_rm_error)
        except:
            pass
        sys.exit(0)

    
    REG_CODE = input("Enter your registration code (or leave empty to set it later): ")
    USERNAME = input("Enter your username (or leave empty to set it later): ")

    main_cli()
