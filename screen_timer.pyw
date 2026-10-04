import time
import ctypes
import tkinter as tk
import psutil
import win32gui
import win32process

CHECK_INTERVAL_SEC = 5         # Chu kỳ quét tối ưu: 5 giây
IDLE_THRESHOLD_SEC = 120       # Quá 2 phút không chạm máy -> tạm dừng đếm
MILESTONE_SEC = 30 * 60        # Mốc nhắc nhở: 30 phút (1800 giây)
POPUP_DURATION_MS = 60 * 1000  # Thông báo 30 phút hiện trong 60 giây
STARTUP_DURATION_MS = 5 * 1000 # Thông báo khởi động hiện trong 5 giây

# API phát hiện thời gian người dùng không thao tác phím/chuột
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_duration():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    return 0.0

class ActiveWindowTracker:
    def __init__(self):
        # Dữ liệu chỉ lưu trong RAM, khởi động lại máy tự reset về 0
        self.usage = {}
        self.notified_milestones = {}
        self.current_app = "desktop"
        self.last_check_time = time.time()

    def get_active_process_name(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "desktop"
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return proc.name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "desktop"

    def tick(self):
        now = time.time()
        elapsed = int(now - self.last_check_time)
        self.last_check_time = now

        # Người dùng rời máy > 2 phút -> không tính thời gian
        if get_idle_duration() >= IDLE_THRESHOLD_SEC:
            return None, 0

        # Tích lũy thời gian cho ứng dụng vừa dùng
        if self.current_app and elapsed > 0:
            self.usage[self.current_app] = self.usage.get(self.current_app, 0) + elapsed

        # Lấy ứng dụng hiện tại cho chu kỳ kế tiếp
        self.current_app = self.get_active_process_name()
        spent = self.usage.get(self.current_app, 0)

        # Kiểm tra mốc 30 phút (30p, 60p, 90p...)
        if self.current_app and self.current_app != "desktop":
            current_stage = spent // MILESTONE_SEC
            last_stage = self.notified_milestones.get(self.current_app, 0)

            if current_stage > last_stage:
                self.notified_milestones[self.current_app] = current_stage
                return self.current_app, spent

        return None, 0


class ReminderApp:
    def __init__(self):
        self.tracker = ActiveWindowTracker()
        
        # Cửa sổ chính ẩn hoàn toàn để làm controller
        self.root = tk.Tk()
        self.root.withdraw()

        self.popup = None
        self.close_timer_id = None

        # Hiện thông báo khởi động lúc vừa bật máy/mở app
        self.show_startup_notification()

        # Bắt đầu vòng lặp quét ứng dụng
        self.check_loop()

    def _create_base_popup(self, width=260, height=95):
        """Khởi tạo khung cửa sổ nổi ở góc dưới bên phải màn hình."""
        self.dismiss_popup()

        self.popup = tk.Toplevel(self.root)
        self.popup.overrideredirect(True)
        self.popup.wm_attributes("-topmost", True)
        self.popup.attributes("-alpha", 0.93)
        self.popup.configure(bg="#1E1E2E")

        screen_w = self.popup.winfo_screenwidth()
        screen_h = self.popup.winfo_screenheight()
        x = screen_w - width - 25
        y = screen_h - height - 65
        self.popup.geometry(f"{width}x{height}+{x}+{y}")
        self.popup.bind("<Double-Button-1>", lambda e: self.dismiss_popup())

    def show_startup_notification(self):
        """Thông báo ngắn gọn khi ứng dụng khởi động thành công."""
        self._create_base_popup(width=250, height=80)

        tk.Label(
            self.popup,
            text="🟢 APP ĐÃ KHỞI CHẠY",
            font=("Segoe UI", 9, "bold"),
            fg="#A6E3A1",
            bg="#1E1E2E"
        ).pack(anchor="w", padx=12, pady=(10, 2))

        tk.Label(
            self.popup,
            text="Bộ theo dõi đang chạy ngầm\nThời gian hôm nay đã được đặt lại về 0.",
            font=("Segoe UI", 9),
            fg="#CDD6F4",
            bg="#1E1E2E",
            justify="left"
        ).pack(anchor="w", padx=12, pady=0)

        # Tự đóng sau 5 giây
        self.close_timer_id = self.root.after(STARTUP_DURATION_MS, self.dismiss_popup)

    def show_reminder_popup(self, app_name, spent_seconds):
        """Thông báo nhắc nhở khi đạt mốc 30 phút."""
        self._create_base_popup(width=260, height=95)

        minutes_spent = spent_seconds // 60
        display_name = app_name if len(app_name) <= 16 else app_name[:13] + "..."

        tk.Label(
            self.popup,
            text="⏳ NHẮC NHỞ NGHỈ NGƠI",
            font=("Segoe UI", 9, "bold"),
            fg="#F38BA8",
            bg="#1E1E2E"
        ).pack(anchor="w", padx=12, pady=(10, 2))

        tk.Label(
            self.popup,
            text=f"Ứng dụng: {display_name}\nĐã dùng: {minutes_spent} phút",
            font=("Segoe UI", 10),
            fg="#CDD6F4",
            bg="#1E1E2E",
            justify="left"
        ).pack(anchor="w", padx=12, pady=0)

        tk.Label(
            self.popup,
            text="(Tự đóng sau 60s - Click đúp để tắt ngay)",
            font=("Segoe UI", 8, "italic"),
            fg="#6C7086",
            bg="#1E1E2E"
        ).pack(anchor="w", padx=12, pady=(4, 0))

        # Tự đóng sau 60 giây
        self.close_timer_id = self.root.after(POPUP_DURATION_MS, self.dismiss_popup)

    def dismiss_popup(self):
        if self.close_timer_id:
            self.root.after_cancel(self.close_timer_id)
            self.close_timer_id = None
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def check_loop(self):
        app_to_notify, spent = self.tracker.tick()
        if app_to_notify:
            self.show_reminder_popup(app_to_notify, spent)

        # Lặp lại sau 5 giây
        self.root.after(CHECK_INTERVAL_SEC * 1000, self.check_loop)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ReminderApp()
    app.run()