import customtkinter as ctk
import json
import threading
import time
import requests
import schedule
import sys
import os
import platform
import traceback

# Windows-only imports guarded
try:
    import winreg
    from PIL import Image, ImageDraw
    from pystray import Icon as TrayIcon, MenuItem as TrayMenuItem, Menu as TrayMenu
    from plyer import notification
except Exception:
    # If running on non-Windows or missing libs, we'll handle gracefully
    winreg = None

def get_base_path():
    
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_path()

# --- 虚拟环境路径 ---
VENV_ACTIVATE_PS1 = r"D:\Local-LLM\AI_Reminder\.venv\Scripts\Activate.ps1"
VENV_PYTHON = VENV_ACTIVATE_PS1.replace('Activate.ps1', 'python.exe')

# --- 绝对路径---
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ICON_PATH = os.path.join(BASE_DIR, "icon.png")  
DEFAULT_PROMPT = "You are a helpful assistant. Please generate a very short, encouraging reminder for me to stay focused and drink water. Keep it under 20 words."
ICON_SIZE = (64, 64)

# --- 多语言文本 ---
LANG = {
    "en": {
        "title": "AI Reminder",
        "settings": "Settings",
        "prompt": "Prompt",
        "api_settings": "API Settings",
        "schedule": "Schedule",
        "model": "Ollama Model",
        "refresh": "Refresh Models",
        "api_base": "API Base URL",
        "api_key": "API Key (Optional)",
        "mode": "Mode",
        "mode_daily": "Daily Time",
        "mode_interval": "Interval (Minutes)",
        "time_val": "Time / Interval",
        "save": "Save & Apply",
        "start_hidden": "Start Minimized",
        "auto_start": "Run on Startup",
        "lang_switch": "Switch to Chinese",
        "status_running": "Status: Running",
        "status_stopped": "Status: Stopped",
        "test_msg": "Test Notification",
        "desc_prompt": "Enter your system prompt here:",
        "tray_show": "Show",
        "tray_quit": "Quit"
    },
    "zh": {
        "title": "AI 提醒助手",
        "settings": "设置",
        "prompt": "提示词",
        "api_settings": "API 设置",
        "schedule": "定时设置",
        "model": "Ollama 模型",
        "refresh": "刷新模型列表",
        "api_base": "API 地址 (Base URL)",
        "api_key": "API 密钥 (选填)",
        "mode": "模式",
        "mode_daily": "每日定时",
        "mode_interval": "开机/间隔 (分钟)",
        "time_val": "时间 / 间隔数值",
        "save": "保存并应用",
        "start_hidden": "启动时隐藏",
        "auto_start": "开机自启",
        "lang_switch": "Switch to English",
        "status_running": "状态: 运行中",
        "status_stopped": "状态: 已停止",
        "test_msg": "测试消息",
        "desc_prompt": "在此输入给 AI 的提示词:",
        "tray_show": "显示窗口",
        "tray_quit": "退出程序"
    }
}

# --- 辅助功能 ---
try:
    from PIL import Image
    def create_default_icon():
        image = Image.new('RGB', ICON_SIZE, (0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((10, 10, 54, 54), fill=(255, 255, 255))
        return image
except Exception:
    def create_default_icon():
        return None


def load_config():
    # 使用绝对路径 CONFIG_FILE
    if not os.path.exists(CONFIG_FILE):
        default_conf = {
            "language": "zh",
            "api_url": "http://localhost:11434/api/generate",
            "api_key": "",
            "model": "llama3",
            "prompt": DEFAULT_PROMPT,
            "mode": "interval",
            "time_value": "60",
            "auto_start": False,
            "theme": "System"
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_conf, f, indent=4)
        return default_conf

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    # 使用绝对路径 CONFIG_FILE
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

# --- 逻辑核心类 ---
class CoreLogic:
    def __init__(self, config):
        self.config = config
        self.scheduler_thread = None
        self.running = True

    def get_ollama_models(self):
        try:
            base_url = self.config.get("api_url", "http://localhost:11434/api/generate")
            tags_url = base_url.replace("/generate", "/tags").replace("/chat/completions", "/models")
            if "localhost" in tags_url:
                resp = requests.get(tags_url, timeout=2)
                if resp.status_code == 200:
                    models = [m['name'] for m in resp.json().get('models', [])]
                    return models
        except Exception:
            pass
        return ["llama3", "mistral", "gemma"]

    def send_notification(self, title, message):
        try:
            if 'plyer' in sys.modules:
                notification.notify(
                    title=title,
                    message=message,
                    app_name="AI Reminder",
                    app_icon=None,
                    timeout=10
                )
            else:
                print(f"NOTIFY: {title} - {message}")
        except Exception as e:
            print(f"Notification Error: {e}")

    def generate_reminder(self):
        print("Generating reminder...")
        prompt = self.config.get("prompt", DEFAULT_PROMPT)
        url = self.config.get("api_url")
        model = self.config.get("model")
        key = self.config.get("api_key")

        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"

        payload = {
            "model": model,
            "stream": False
        }

        if "v1/chat/completions" in (url or ""):
            payload["messages"] = [{"role": "user", "content": prompt}]
        else:
            payload["prompt"] = prompt

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                content = ""
                if isinstance(data, dict):
                    if "response" in data:
                        content = data["response"]
                    elif "choices" in data:
                        # OpenAI-style
                        try:
                            content = data["choices"][0]["message"]["content"]
                        except Exception:
                            content = str(data)
                else:
                    content = str(data)

                content = (content or "Reminder").strip()
                self.send_notification("AI Reminder", content)
            else:
                self.send_notification("Error", f"API Error: {resp.status_code}")
        except Exception as e:
            self.send_notification("Error", f"Connection failed: {str(e)}")

    def schedule_job(self):
        schedule.clear()
        mode = self.config.get("mode")
        val = self.config.get("time_value")

        if mode == "daily":
            try:
                schedule.every().day.at(val).do(self.generate_reminder)
            except Exception:
                print("Invalid daily time format. Expected HH:MM")
        else:
            try:
                mins = int(val)
                if mins <= 0:
                    mins = 60
                schedule.every(mins).minutes.do(self.generate_reminder)
            except Exception:
                print("Invalid interval value, must be integer minutes")

    def start_scheduler(self):
        self.schedule_job()

        def run_loop():
            while self.running:
                try:
                    schedule.run_pending()
                except Exception:
                    traceback.print_exc()
                time.sleep(1)

        self.scheduler_thread = threading.Thread(target=run_loop, daemon=True)
        self.scheduler_thread.start()

# --- GUI 类 ---
class App(ctk.CTk):
    def __init__(self, config, core, start_minimized=False):
        super().__init__()
        self.config = config
        self.core = core
        self.lang_code = config.get("language", "zh")
        self.txt = LANG[self.lang_code]

        # 重启标记
        self.should_restart = False

        # 窗口设置
        self.title(self.txt["title"])
        self.geometry("500x600")
        ctk.set_appearance_mode(config.get('theme', 'System'))
        ctk.set_default_color_theme("dark-blue")

        self.protocol("WM_DELETE_WINDOW", self.on_close_window)

        self.create_widgets()

        if start_minimized:
            self.withdraw()

        # 托盘需要在主线程外运行
        try:
            self.setup_tray()
        except Exception as e:
            print("Tray setup failed:", e)

    def create_widgets(self):
        # 语言切换
        self.btn_lang = ctk.CTkButton(self, text=self.txt["lang_switch"], command=self.toggle_language, fg_color="transparent", border_width=1, text_color=("black", "white"))
        self.btn_lang.pack(pady=10, padx=10, anchor="ne")

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=20, pady=10, fill="both", expand=True)

        self.tab_settings = self.tabview.add(self.txt["api_settings"])
        self.tab_prompt = self.tabview.add(self.txt["prompt"])
        self.tab_schedule = self.tabview.add(self.txt["schedule"])

        # API 设置
        ctk.CTkLabel(self.tab_settings, text=self.txt["api_base"]).pack(pady=5)
        self.entry_api = ctk.CTkEntry(self.tab_settings, width=300)
        self.entry_api.insert(0, self.config.get("api_url", ""))
        self.entry_api.pack(pady=5)

        ctk.CTkLabel(self.tab_settings, text=self.txt["api_key"]).pack(pady=5)
        self.entry_key = ctk.CTkEntry(self.tab_settings, width=300, show="*")
        self.entry_key.insert(0, self.config.get("api_key", ""))
        self.entry_key.pack(pady=5)

        ctk.CTkLabel(self.tab_settings, text=self.txt["model"]).pack(pady=5)
        self.combo_model = ctk.CTkComboBox(self.tab_settings, values=[self.config.get("model", "llama3")])
        self.combo_model.pack(pady=5)
        self.btn_refresh = ctk.CTkButton(self.tab_settings, text=self.txt["refresh"], command=self.refresh_models)
        self.btn_refresh.pack(pady=5)

        # 提示词
        ctk.CTkLabel(self.tab_prompt, text=self.txt["desc_prompt"]).pack(pady=5, anchor="w")
        self.text_prompt = ctk.CTkTextbox(self.tab_prompt, height=200)
        self.text_prompt.insert("0.0", self.config.get("prompt", ""))
        self.text_prompt.pack(pady=5, fill="x")

        # 定时设置
        self.var_mode = ctk.StringVar(value=self.config.get("mode", "interval"))
        ctk.CTkRadioButton(self.tab_schedule, text=self.txt["mode_daily"], variable=self.var_mode, value="daily").pack(pady=5)
        ctk.CTkRadioButton(self.tab_schedule, text=self.txt["mode_interval"], variable=self.var_mode, value="interval").pack(pady=5)

        ctk.CTkLabel(self.tab_schedule, text=self.txt["time_val"]).pack(pady=5)
        self.entry_time = ctk.CTkEntry(self.tab_schedule)
        self.entry_time.insert(0, self.config.get("time_value", "60"))
        self.entry_time.pack(pady=5)

        # 底部
        self.check_autostart = ctk.CTkCheckBox(self, text=self.txt["auto_start"], command=self.toggle_autostart)
        if self.config.get("auto_start"):
            self.check_autostart.select()
        self.check_autostart.pack(pady=5)

        self.btn_test = ctk.CTkButton(self, text=self.txt["test_msg"], command=lambda: threading.Thread(target=self.core.generate_reminder).start())
        self.btn_test.pack(pady=5)

        self.btn_save = ctk.CTkButton(self, text=self.txt["save"], command=lambda: self.save_settings(True), fg_color="black", hover_color="gray")
        self.btn_save.pack(pady=10)

        # 初始化
        self.refresh_models()

    def refresh_models(self):
        try:
            models = self.core.get_ollama_models()
            self.combo_model.configure(values=models)
            if models:
                self.combo_model.set(models[0])
        except Exception as e:
            print("Refresh models failed:", e)

    def toggle_language(self):
        new_lang = "en" if self.lang_code == "zh" else "zh"
        self.config["language"] = new_lang
        self.save_settings(show_toast=False)
        self.should_restart = True
        self.close_app_completely()

    def save_settings(self, show_toast=True):
        self.config["api_url"] = self.entry_api.get()
        self.config["api_key"] = self.entry_key.get()
        self.config["model"] = self.combo_model.get()
        self.config["prompt"] = self.text_prompt.get("0.0", "end").strip()
        self.config["mode"] = self.var_mode.get()
        self.config["time_value"] = self.entry_time.get()
        self.config["auto_start"] = bool(self.check_autostart.get())

        save_config(self.config)
        self.core.config = self.config
        self.core.schedule_job()
        if show_toast:
            print("Settings Saved")

    def toggle_autostart(self):
        """
        为了兼容多种启动方式：
        1) 如果打包为 exe（sys.frozen），我们在注册表写入 exe 的路径。
        2) 如果未打包，尽量使用你提供的虚拟环境 python（VENV_PYTHON）来建立开机启动。
        3) 如果注册表写入失败，会在当前用户的 Startup 文件夹创建一个 .bat 作为回退。
        """
        app_name = "AI_Reminder"

        # 组装启动命令
        if getattr(sys, 'frozen', False):
            # 被打包为 exe，直接运行 exe
            start_cmd = f'"{os.path.abspath(sys.executable)}" --minimized'
            # target_path 不变
        else:
            # 运行于 python 脚本，优先使用虚拟环境的 python（如果存在）
            venv_py = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
            script = os.path.abspath(sys.argv[0])
            start_cmd = f'"{venv_py}" "{script}" --minimized'

        # 尝试写入注册表（Windows）
        if winreg is not None and platform.system() == 'Windows':
            try:
                access = winreg.KEY_ALL_ACCESS
                # KEY_WOW64_64KEY 可能不存在于某些环境，安全获取
                try:
                    access = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY
                except Exception:
                    pass

                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, access)

                if self.check_autostart.get():
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, start_cmd)
                    print("Registry autostart set:", start_cmd)
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                        print("Registry autostart removed")
                    except FileNotFoundError:
                        pass

                winreg.CloseKey(key)
                # 同步配置
                self.config['auto_start'] = bool(self.check_autostart.get())
                save_config(self.config)
                return
            except Exception as e:
                print("Registry write failed, falling back to Startup folder:", e)

        # 回退方案：在 Startup 文件夹放一个 .bat
        try:
            startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
            if not os.path.isdir(startup_dir):
                os.makedirs(startup_dir, exist_ok=True)

            bat_path = os.path.join(startup_dir, "AI_Reminder_start.bat")

            if self.check_autostart.get():
                with open(bat_path, 'w', encoding='utf-8') as f:
                    # 使用 start 为了不阻塞启动
                    f.write(f'@echo off\nstart "" {start_cmd}\n')
                print("Startup batch created at", bat_path)
            else:
                if os.path.exists(bat_path):
                    os.remove(bat_path)
                    print("Startup batch removed", bat_path)

            self.config['auto_start'] = bool(self.check_autostart.get())
            save_config(self.config)
        except Exception as e:
            print("Creating startup batch failed:", e)

    def on_close_window(self):
        self.withdraw()

    def setup_tray(self):
        def show_window(icon, item):
            try:
                self.deiconify()
                self.lift()
            except Exception:
                pass

        def quit_app_tray(icon, item):
            self.should_restart = False
            self.close_app_completely()

        # 尝试加载 icon.png (使用全局变量 ICON_PATH)
        image = None
        try:
            if os.path.exists(ICON_PATH):
                image = Image.open(ICON_PATH)
            else:
                image = create_default_icon()
        except Exception:
            image = None

        menu = TrayMenu(
            TrayMenuItem(self.txt["tray_show"], show_window, default=True),
            TrayMenuItem(self.txt["tray_quit"], quit_app_tray)
        )

        self.tray_icon = TrayIcon("AI Reminder", image, "AI Reminder", menu)
        # pystray 的 run 会阻塞，所以我们在线程中调用
        t = threading.Thread(target=self.tray_icon.run, daemon=True)
        t.start()

    def close_app_completely(self):
        # 1. 停止后台逻辑
        try:
            self.core.running = False
            # 给线程一点时间退出
            if self.core.scheduler_thread and self.core.scheduler_thread.is_alive():
                self.core.scheduler_thread.join(timeout=1)
        except Exception:
            pass

        # 2. 停止托盘图标
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass
        except Exception:
            pass

        # 3. 退出 GUI
        try:
            self.quit()
            self.destroy()
        except Exception:
            pass

# --- 主逻辑循环 ---

def main():
    start_minimized = "--minimized" in sys.argv

    while True:
        config = load_config()

        core = CoreLogic(config)
        core.start_scheduler()

        # 如果用户在 config 中勾选了 autostart，但程序没有在 Windows 中注册，界面中会显示勾选状态。
        app = App(config, core, start_minimized=start_minimized)
        try:
            app.mainloop()
        except Exception as e:
            print("Mainloop exception:", e)

        if app.should_restart:
            print("Reloading application for language switch...")
            start_minimized = False
            time.sleep(0.5)
            continue
        else:
            break

    print("Application exited.")
    sys.exit()


if __name__ == "__main__":
    main()