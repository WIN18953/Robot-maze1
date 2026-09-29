"""
gui.py — ระบบควบคุมภารกิจกู้ภัย (CustomTkinter Edition - ธีมภาษาไทย)
"""
import datetime
import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

import config as C
from grid_map import GridMap, random_maze, DIRS, DX, DY, WALL, OPEN, UNKNOWN

HERE = os.path.dirname(os.path.abspath(__file__))
CANVAS = 620
PAD = 30

# ตั้งค่า Theme ของโปรแกรม
ctk.set_appearance_mode("dark")  # ธีมมืด (Dark Mode)
ctk.set_default_color_theme("blue")  # โทนสีฟ้า

class App:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("ระบบควบคุมภารกิจกู้ภัย - Assignment 2 (Team Edition)") 
        global CANVAS
        CANVAS = max(380, min(620, self.root.winfo_screenheight() - 300))
        self.q = queue.Queue()
        self._log_lock = threading.Lock()
        os.makedirs(os.path.join(HERE, C.OUTPUT_DIR), exist_ok=True)
        self._session_log_path = os.path.join(
            HERE, C.OUTPUT_DIR, "gui_session_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")
        self._session_log_file = open(self._session_log_path, "w", encoding="utf-8")
        self.robot = None
        self.explorer = None
        self.logger = None
        self.worker = None
        self.stop_event = threading.Event()
        self.gt = None
        self.out_dir = None
        self.robot_kind = None
        self.m = GridMap(C.GRID_W, C.GRID_H, C.CELL_M)
        self.last_eval = None
        self._build()
        self.log(C.build_info())
        self._new_sim_world()
        self.redraw()
        self.root.after(100, self._poll)

    # ================================================================ UI
    def _build(self):
        left = ctk.CTkFrame(self.root, fg_color="transparent")
        left.pack(side=tk.LEFT, fill=tk.Y, padx=15, pady=15)
        right = ctk.CTkFrame(self.root, fg_color="transparent")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=15)

        # ---- 1) Settings ----
        ctk.CTkLabel(left, text="[ 1. ตั้งค่าระบบและพารามิเตอร์ ]", font=("Segoe UI", 14, "bold"), text_color="#4FC3F7").pack(anchor="w", pady=(0, 5))
        f = ctk.CTkFrame(left)
        f.pack(fill=tk.X, pady=(0, 15), ipadx=5, ipady=5)
        
        self.v_w = ctk.IntVar(value=C.GRID_W)
        self.v_h = ctk.IntVar(value=C.GRID_H)
        self.v_cell = ctk.DoubleVar(value=C.CELL_M)
        self.v_sx = ctk.IntVar(value=C.START_X)
        self.v_sy = ctk.IntVar(value=C.START_Y)
        self.v_hd = ctk.StringVar(value=C.START_HEADING)
        self.v_mode = ctk.StringVar(value="sim")
        self.v_seed = ctk.StringVar(value="")
        self.v_move = ctk.StringVar(value=C.MOVE_MODE)
        
        rows = [("กว้าง (ช่อง)", ctk.CTkEntry(f, textvariable=self.v_w, width=70)),
                ("สูง (ช่อง)", ctk.CTkEntry(f, textvariable=self.v_h, width=70)),
                ("ขนาดช่อง (m)", ctk.CTkEntry(f, textvariable=self.v_cell, width=70)),
                ("จุดเริ่ม X", ctk.CTkEntry(f, textvariable=self.v_sx, width=70)),
                ("จุดเริ่ม Y", ctk.CTkEntry(f, textvariable=self.v_sy, width=70)),
                ("ทิศทางเริ่มต้น", ctk.CTkOptionMenu(f, variable=self.v_hd, values=DIRS, width=80)),
                ("การเคลื่อนที่", ctk.CTkOptionMenu(f, variable=self.v_move, values=["strafe", "rotate"], width=80)),
                ("Sim Seed", ctk.CTkEntry(f, textvariable=self.v_seed, width=70))]
        
        for i, (lab, w) in enumerate(rows):
            r, c = divmod(i, 2)
            ctk.CTkLabel(f, text=lab).grid(row=r, column=2 * c, sticky="w", padx=(10 if c == 0 else 15, 5), pady=5)
            w.grid(row=r, column=2 * c + 1, sticky="w", pady=5)
            
        nr = (len(rows) + 1) // 2
        mf = ctk.CTkFrame(f, fg_color="transparent")
        mf.grid(row=nr, column=0, columnspan=4, sticky="w", padx=10, pady=5)
        ctk.CTkRadioButton(mf, text="จำลอง (Sim)", value="sim", variable=self.v_mode).pack(side=tk.LEFT, padx=(0, 15))
        ctk.CTkRadioButton(mf, text="หุ่นยนต์จริง", value="real", variable=self.v_mode).pack(side=tk.LEFT)
        
        ctk.CTkButton(f, text="ยืนยันการตั้งค่า / เชื่อมต่อหุ่น", command=self.apply_settings, fg_color="#2E7D32", hover_color="#1B5E20").grid(
            row=nr + 1, column=0, columnspan=4, sticky="ew", padx=10, pady=10)

        # ---- 2) Mission ----
        ctk.CTkLabel(left, text="[ 2. ศูนย์ควบคุมภารกิจ ]", font=("Segoe UI", 14, "bold"), text_color="#4FC3F7").pack(anchor="w", pady=(0, 5))
        f2 = ctk.CTkFrame(left)
        f2.pack(fill=tk.X, pady=(0, 15), ipadx=5, ipady=5)
        
        self.btn_explore = ctk.CTkButton(f2, text="▶ เริ่มสำรวจ (Auto-Explore)", command=self.start_explore, fg_color="#1976D2")
        self.btn_explore.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(f2, text="■ หยุดฉุกเฉิน (STOP)", command=self.stop, fg_color="#D32F2F", hover_color="#B71C1C").grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(f2, text="สแกนพื้นที่ตรงนี้", command=self.scan_here).grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(f2, text="ฉันอยู่ที่ไหน? (Locate)", command=self.where_am_i).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(f2, text="กลับจุดเริ่มต้น (Home)", command=self.go_home).grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(f2, text="ปรับเทียบ ToF", command=self.calibrate, fg_color="#E65100", hover_color="#EF6C00").grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        f2.columnconfigure(0, weight=1); f2.columnconfigure(1, weight=1)

        # ---- 3) Map Interaction ----
        ctk.CTkLabel(left, text="[ 3. โต้ตอบกับแผนที่ ]", font=("Segoe UI", 14, "bold"), text_color="#4FC3F7").pack(anchor="w", pady=(0, 5))
        f3 = ctk.CTkFrame(left)
        f3.pack(fill=tk.X, pady=(0, 15), ipadx=5, ipady=5)
        
        self.v_click = ctk.StringVar(value="goto")
        for val, txt in (("goto", "ไปยังเป้าหมาย (คลิกช่องเพื่อเดินไป)"), ("pose", "ตั้งตำแหน่งหุ่น (บังคับวางหุ่น)"),
                         ("edit", "แก้ไขกำแพง (คลิกที่เส้นขอบ)"), ("gt", "วาดเฉลย (Ground Truth)")):
            ctk.CTkRadioButton(f3, text=txt, value=val, variable=self.v_click, command=self.redraw).pack(anchor="w", padx=10, pady=5)

        # ---- 4) File / Eval ----
        ctk.CTkLabel(left, text="[ 4. จัดการไฟล์และประเมินผล ]", font=("Segoe UI", 14, "bold"), text_color="#4FC3F7").pack(anchor="w", pady=(0, 5))
        f4 = ctk.CTkFrame(left)
        f4.pack(fill=tk.X, pady=(0, 5), ipadx=5, ipady=5)
        
        g = ctk.CTkFrame(f4, fg_color="transparent")
        g.pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(g, text="บันทึกแผนที่", command=self.save_map).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ctk.CTkButton(g, text="โหลดแผนที่", command=self.load_map).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        ctk.CTkButton(g, text="บันทึก GT", command=self.save_gt).grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        ctk.CTkButton(g, text="โหลด GT", command=self.load_gt).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        ctk.CTkButton(g, text="ล้างข้อมูล GT", command=self.clear_gt, fg_color="#546E7A").grid(row=2, column=0, columnspan=2, sticky="ew", padx=2, pady=2)
        g.columnconfigure(0, weight=1); g.columnconfigure(1, weight=1)
        
        ctk.CTkButton(f4, text="📊 ประเมินผล & ส่งออกไฟล์", command=self.evaluate_export, fg_color="#4527A0", hover_color="#311B92").pack(fill=tk.X, padx=10, pady=(0, 5))
        self.v_showgt = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(f4, text="ซ้อนทับเฉลย (แสดงจุดผิดพลาดสีแดง)", variable=self.v_showgt, command=self.redraw).pack(anchor="w", padx=10, pady=5)

        # ---- Canvas + Log ----
        self.status = ctk.StringVar(value="[ ระบบพร้อมทำงาน ]")
        ctk.CTkLabel(right, textvariable=self.status, font=("Consolas", 14, "bold"), text_color="#00E676").pack(anchor="w", pady=(0, 5))
        
        # ปรับสี Canvas ให้กลืนกับธีมมืด
        self.cv = tk.Canvas(right, width=CANVAS, height=CANVAS, bg="#1E1E1E", highlightthickness=2, highlightbackground="#333333")
        self.cv.pack()
        self.cv.bind("<Button-1>", self.on_click)
        
        # Log Console สไตล์ Hacker
        self.logbox = ctk.CTkTextbox(right, height=150, font=("Consolas", 12), text_color="#00FF00", fg_color="#0A0A0A", border_color="#333333", border_width=2)
        self.logbox.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

    # ================================================================ helpers
    def log(self, s):
        with self._log_lock:
            try:
                self._session_log_file.write(s + "\n")
                self._session_log_file.flush()
            except Exception:
                pass
        self.q.put(("log", s))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.logbox.insert(tk.END, val + "\n")
                    self.logbox.see(tk.END)
                elif kind == "redraw":
                    pass
                elif kind == "done":
                    self.btn_explore.configure(state="normal")
                elif kind == "info":
                    messagebox.showinfo("ผลลัพธ์", val)
        except queue.Empty:
            pass
        self.redraw()
        self.root.after(150, self._poll)

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def run_bg(self, fn, name):
        if self.busy():
            messagebox.showwarning("กำลังทำงาน", "หุ่นกำลังทำงานอยู่ กรุณากด Stop ก่อน")
            return
        if self.robot is None:
            messagebox.showwarning("ไม่ได้เชื่อมต่อ", "กรุณากด 'ยืนยันการตั้งค่า / เชื่อมต่อหุ่น' ก่อนเริ่ม")
            return
        if self.robot_kind != self.v_mode.get():
            messagebox.showwarning(
                "โหมดไม่ตรงกัน",
                "กรุณากด 'ยืนยันการตั้งค่า / เชื่อมต่อหุ่น' อีกครั้งเพื่อสลับโหมดให้ถูกต้อง")
            return
        self.stop_event.clear()
        self._ensure_logger()
        from explorer import Explorer
        self.explorer = Explorer(self.robot, self.m, self.logger, stop_event=self.stop_event, echo=self.log)
        def wrap():
            try:
                fn()
            except Exception as e:
                self.log("ข้อผิดพลาด (ERROR): " + repr(e))
                self.log(traceback.format_exc())
            finally:
                self.q.put(("done", None))
        self.log(f"--- {name} ---")
        self.worker = threading.Thread(target=wrap, daemon=True)
        self.worker.start()

    def _ensure_logger(self):
        if self.logger is None:
            from explorer import RunLogger
            self.out_dir = os.path.join(HERE, C.OUTPUT_DIR,
                                        "run_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            self.logger = RunLogger(self.out_dir, echo=self.log)
            self.log(f"บันทึก log ที่ -> {self.out_dir}")

    def _read_settings(self):
        w, h = int(self.v_w.get()), int(self.v_h.get())
        if not (2 <= w <= C.MAX_GRID and 2 <= h <= C.MAX_GRID):
            raise ValueError(f"ขนาดตารางต้องอยู่ระหว่าง 2..{C.MAX_GRID}")
        sx, sy = int(self.v_sx.get()), int(self.v_sy.get())
        if not (0 <= sx < w and 0 <= sy < h):
            raise ValueError("จุดเริ่มต้นอยู่นอกเขตพื้นที่")
        return w, h, float(self.v_cell.get()), sx, sy, self.v_hd.get()

    def _new_sim_world(self):
        seed = self.v_seed.get().strip()
        self.sim_world = random_maze(self.m.w, self.m.h, seed=int(seed) if seed else None)

    # ================================================================ actions
    def apply_settings(self):
        if self.busy():
            messagebox.showwarning("ระบบไม่ว่าง", "กรุณากด Stop ก่อน"); return
        try:
            w, h, cell, sx, sy, hd = self._read_settings()
        except Exception as e:
            messagebox.showerror("ตั้งค่าผิดพลาด", str(e)); return
        C.MOVE_MODE = self.v_move.get()
        if self.robot:
            self.robot.close(); self.robot = None
        self.robot_kind = None
        if self.logger:
            self.logger.close(); self.logger = None
        self.m = GridMap(w, h, cell)
        if self.gt is not None and (self.gt.w, self.gt.h) != (w, h):
            self.gt = None
        self.last_eval = None
        if self.v_mode.get() == "sim":
            from robots import SimRobot
            if self.gt is not None and not getattr(self, "gt_is_random", False):
                world = self.gt
                self.log("โหมด Sim: ดึง Ground Truth ที่ตั้งไว้มาใช้งานแล้ว")
            else:
                self._new_sim_world(); world = self.sim_world
                self.log("โหมด Sim: ใช้เขาวงกตแบบสุ่ม")
            seed = self.v_seed.get().strip()
            self.robot = SimRobot(world, sx, sy, hd, cell, seed=int(seed) if seed else None)
            self.robot_kind = "sim"
            if world is self.sim_world:
                self.gt = world
                self.gt_is_random = True
            self.log(f"[SIM] จำลองสำเร็จ: {w}x{h}, ขนาด {cell} m/ช่อง, เริ่มที่ ({sx},{sy}) หันทิศ {hd}")
        else:
            self.status.set("กำลังเชื่อมต่อสัญญาณ RoboMaster...")
            def conn():
                try:
                    from robots import RealRobot
                    r = RealRobot(sx, sy, hd, cell, log=self.log)
                    self.robot = r
                    self.robot_kind = "real"
                    self.log(f"[REAL] เชื่อมต่อหุ่นจริงสำเร็จ: {w}x{h}, เริ่ม ({sx},{sy}) หันทิศ {hd}")
                except Exception as e:
                    self.robot = None
                    self.robot_kind = None
                    self.log("เชื่อมต่อล้มเหลว: " + repr(e))
            threading.Thread(target=conn, daemon=True).start()

    def start_explore(self):
        if self.busy():
            messagebox.showwarning("ระบบไม่ว่าง", "กรุณากด Stop ก่อน"); return
        self.m = GridMap(self.m.w, self.m.h, self.m.cell_m)
        self.last_eval = None
        def job():
            vis, tot = self.explorer.explore()
            self.log(f"จบการสำรวจ: ครอบคลุม {vis}/{tot} ช่อง | เริ่ม {self.m.start} จบ {self.m.end}")
            self._export(auto=True)
        self.run_bg(job, "EXPLORE")

    def stop(self):
        self.stop_event.set()
        self.log("กำลังส่งคำสั่งหยุดฉุกเฉิน...")

    def scan_here(self):
        self.run_bg(lambda: (self.explorer._sense_here(), None), "SCAN")

    def where_am_i(self):
        def job():
            obs, cands = self.explorer.where_am_i()
            seen = "".join("W" if obs[d] == WALL else "." for d in range(4))
            best = [c for m_, c in cands if m_ == 0]
            self.log(f"พบกำแพง N,E,S,W = {seen}  -> จุดที่เป็นไปได้: {best if best else cands[:3]}")
            self.log(f"ตำแหน่งที่คำนวณได้: {self.robot.cell}")
        self.run_bg(job, "RELOCALIZE")

    def go_home(self):
        if not self.m.start:
            messagebox.showinfo("", "ไม่พบข้อมูลจุดเริ่มต้น"); return
        tgt = tuple(self.m.start[:2])
        self.run_bg(lambda: self.explorer.go_to(tgt), f"GO HOME {tgt}")

    def calibrate(self):
        def job():
            detailed = self.robot.scan_all_detailed()
            for d in range(4):
                samples_txt = ", ".join(f"{v:.0f}" for v in detailed[d]["samples"])
                lo, hi = min(detailed[d]["samples"]), max(detailed[d]["samples"])
                self.log(f"[CALIBRATE] ทิศ {DIRS[d]}: [{samples_txt}]mm -> ค่ากลาง (median)={detailed[d]['median']:.0f}mm")
            tof = {d: detailed[d]["median"] for d in range(4)}
            near = {d: v for d, v in tof.items() if v < 600}
            pairs = [(near[d] + near[d + 2]) / 2 for d in (0, 1) if d in near and d + 2 in near]
            if pairs:
                e = sum(pairs) / len(pairs)
                C.WALL_EXPECT_MM = round(e)
                C.WALL_THRESHOLD_MM = round(e + C.WALL_THRESHOLD_FRAC * self.m.cell_m * 1000)
                self.log(f"บันทึกค่า WALL_EXPECT_MM={C.WALL_EXPECT_MM}, WALL_THRESHOLD_MM={C.WALL_THRESHOLD_MM}")
            else:
                self.log(f"[CALIBRATE] ไม่พบคู่กำแพงที่อยู่ตรงข้ามกัน ใช้ค่าเดิมต่อไป")
            
            disagree, sides = 0, 0
            for d in range(4):
                sh = self.robot.read_sharp(d)
                if sh is None:
                    continue
                sides += 1
                side = "R" if (d - self.robot.body_heading) % 4 == 1 else "L"
                od = (d + 2) % 4
                if sh[0] < C.SHARP_WALL_MM and d in near and od in near:
                    lean = (tof[od] - tof[d]) / 2.0
                    ex = round(sh[0] + lean)
                    setattr(C, f"SHARP_{side}_EXPECT_MM", ex)
                    self.log(f"[CALIBRATE] Sharp ฝั่ง {side} = {sh[0]:.0f}mm -> ปรับค่า EXPECT={ex}")
        self.run_bg(job, "CALIBRATE")

    # ---------------------------------------------------------------- click
    def _geom(self):
        s = (CANVAS - 2 * PAD) / max(self.m.w, self.m.h)
        ox = (CANVAS - s * self.m.w) / 2
        oy = (CANVAS - s * self.m.h) / 2
        return s, ox, oy

    def _px(self, gx, gy):
        s, ox, oy = self._geom()
        return ox + gx * s, CANVAS - (oy + gy * s)

    def on_click(self, ev):
        s, ox, oy = self._geom()
        gx = (ev.x - ox) / s
        gy = (CANVAS - ev.y - oy) / s
        mode = self.v_click.get()
        cx, cy = int(gx // 1), int(gy // 1)
        if mode in ("goto", "pose"):
            if not self.m.in_bounds(cx, cy):
                return
            if mode == "goto":
                if self.robot is None:
                    return
                self.run_bg(lambda: self.explorer.go_to((cx, cy)), f"GOTO ({cx},{cy})")
            else:
                if self.busy():
                    return
                if self.robot:
                    self.robot.set_pose(cx, cy, self.v_hd.get())
                self.v_sx.set(cx); self.v_sy.set(cy)
                self.log(f"บังคับตั้งค่าตำแหน่ง = ({cx},{cy}) หันหน้าไปทิศ {self.v_hd.get()}")
            return
        fx, fy = gx - cx, gy - cy
        cands = [(fy, 2), (1 - fy, 0), (fx, 3), (1 - fx, 1)]
        dist, d = min(cands)
        if dist > 0.25:
            return
        x, y = cx, cy
        if not self.m.in_bounds(x, y):
            x, y = min(max(cx, 0), self.m.w - 1), min(max(cy, 0), self.m.h - 1)
            d = 0 if cy >= self.m.h else 1 if cx >= self.m.w else 2 if cy < 0 else 3
        target = self.m if mode == "edit" else self._gt_for_edit()
        cur = target.state(x, y, d)
        if mode == "edit":
            nxt = {WALL: OPEN, OPEN: UNKNOWN, UNKNOWN: WALL}[cur]
        else:
            nxt = OPEN if cur == WALL else WALL
        target.set_state(x, y, d, nxt)
        if target.is_boundary(x, y, d):
            target.boundary_walls = False
        self.redraw()

    def _gt_for_edit(self):
        if self.gt is None or (self.gt.w, self.gt.h) != (self.m.w, self.m.h):
            self.clear_gt()
        return self.gt

    # ---------------------------------------------------------------- files
    def save_map(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", initialdir=HERE,
                                         initialfile="my_map.json", filetypes=[("Map JSON", "*.json")])
        if p:
            self.m.save(p); self.log(f"บันทึกแผนที่ไปที่ -> {p}")

    def load_map(self):
        if self.busy(): return
        p = filedialog.askopenfilename(initialdir=HERE, filetypes=[("Map JSON", "*.json")])
        if not p: return
        m = GridMap.load(p)
        self.m = m
        self.v_w.set(m.w); self.v_h.set(m.h); self.v_cell.set(m.cell_m)
        self.log(f"โหลดแผนที่จากไฟล์ {p}")
        if self.robot is not None and self.explorer is not None:
            self.explorer.m = m
        if self.robot is None:
            self._pending_map = m

    def save_gt(self):
        if self.gt is None: return
        p = filedialog.asksaveasfilename(defaultextension=".json", initialdir=HERE,
                                         initialfile="ground_truth.json", filetypes=[("JSON", "*.json")])
        if p: self.gt.save(p); self.log(f"บันทึกข้อมูล GT ไปที่ -> {p}")

    def load_gt(self):
        p = filedialog.askopenfilename(initialdir=HERE, filetypes=[("JSON", "*.json")])
        if p:
            g = GridMap.load(p)
            self.gt = g; self.gt_is_random = False
            self.v_showgt.set(True); self.log(f"โหลดข้อมูล GT จากไฟล์ {p}")

    def clear_gt(self):
        g = GridMap(self.m.w, self.m.h, self.m.cell_m, boundary_walls=True)
        for x in range(g.w):
            for y in range(g.h):
                for d in range(4):
                    if not g.is_boundary(x, y, d):
                        g.set_state(x, y, d, OPEN)
        self.gt = g
        self.gt_is_random = False
        self.v_showgt.set(True)

    def evaluate_export(self):
        self._export(auto=False)

    def _export(self, auto):
        from evaluation import export_all
        try:
            self._ensure_logger()
            gt = self.gt if (self.gt is not None and (self.gt.w, self.gt.h) == (self.m.w, self.m.h)) else None
            res, text = export_all(self.m, self.logger.traj, self.out_dir, gt)
            self.last_eval = res
            self.log(text)
            if not auto:
                msg = f"ครอบคลุมพื้นที่ (Coverage) {res['coverage_pct']}%\n"
                if "map_accuracy_pct" in res: msg += f"ความแม่นยำแผนที่ (Accuracy) {res['map_accuracy_pct']}%"
                self.q.put(("info", msg))
        except Exception as e:
            self.log("เกิดข้อผิดพลาดในการส่งออกไฟล์: " + repr(e))

    # ================================================================ draw
    def redraw(self):
        if hasattr(self, "_pending_map") and self.robot is not None:
            self.m = self._pending_map
            del self._pending_map
        cv = self.cv
        cv.delete("all")
        m = self.m
        s, ox, oy = self._geom()
        mode = self.v_click.get()
        show = self.gt if mode == "gt" else m
        cell_ok = None
        if self.last_eval and "cell_ok" in self.last_eval and mode != "gt":
            if len(self.last_eval["cell_ok"]) == m.w:
                cell_ok = self.last_eval["cell_ok"]
                
        # วาดพื้นหลังช่องตาราง
        for x in range(m.w):
            for y in range(m.h):
                x0, y0 = self._px(x, y + 1); x1, y1 = self._px(x + 1, y)
                fc = "#1B5E20" if (m.visited[x][y] and mode != "gt") else "#2B2B2B"
                if cell_ok is not None:
                    fc = "#2E7D32" if cell_ok[x][y] else "#880E4F"
                cv.create_rectangle(x0, y0, x1, y1, fill=fc, outline="#424242")
                cv.create_text(x0 + 4, y1 - 4, text=f"{x},{y}", anchor="sw", fill="#757575", font=("Arial", 8))
                
        if self.explorer and self.explorer.plan and mode != "gt":
            pts = []
            for (x, y) in self.explorer.plan:
                pts += list(self._px(x + 0.5, y + 0.5))
            if len(pts) >= 4:
                cv.create_line(*pts, fill="#00E5FF", width=4, dash=(6, 4), arrow=tk.LAST)
                
        if self.logger and self.logger.traj and mode != "gt":
            pts = []
            for p in self.logger.traj[-600:]:
                pts += list(self._px(p[1] / m.cell_m, p[2] / m.cell_m))
            if len(pts) >= 4:
                cv.create_line(*pts, fill="#29B6F6", width=2)
                
        if show is not None:
            for x in range(m.w):
                for y in range(m.h):
                    for d in range(4):
                        if d in (0, 1) or (d == 2 and y == 0) or (d == 3 and x == 0):
                            self._draw_edge(show, x, y, d, mode)
                            
        if m.start:
            px, py = self._px(m.start[0] + 0.5, m.start[1] + 0.5)
            cv.create_oval(px - 16, py - 16, px + 16, py + 16, outline="#4CAF50", width=3)
            cv.create_text(px, py - 24, text="จุดเริ่ม", fill="#4CAF50", font=("Arial", 9, "bold"))
        if m.end:
            px, py = self._px(m.end[0] + 0.5, m.end[1] + 0.5)
            cv.create_text(px, py + 24, text="สิ้นสุด", fill="#F44336", font=("Arial", 9, "bold"))
            
        if self.robot is not None:
            ex, ey = self.robot.est_xy()
            px, py = self._px(ex / m.cell_m, ey / m.cell_m)
            h = self.robot.heading
            r = s * 0.28
            fx, fy = DX[h], -DY[h]
            lx, ly = -fy, fx
            pts = [px + fx * r, py + fy * r,
                   px - fx * r * 0.7 + lx * r * 0.7, py - fy * r * 0.7 + ly * r * 0.7,
                   px - fx * r * 0.7 - lx * r * 0.7, py - fy * r * 0.7 - ly * r * 0.7]
            cv.create_polygon(*pts, fill="#FF9800", outline="#E65100", width=2)
            if self.explorer and self.explorer.last_tof:
                for d, v in self.explorer.last_tof.items():
                    if not isinstance(d, int): continue
                    L = min(v, 2500) / 1000.0 / m.cell_m * s
                    cv.create_line(px, py, px + DX[d] * L, py - DY[d] * L, fill="#FFCC80", width=1)
                    
        vis, tot = m.counts()
        acc = ""
        if self.last_eval and "map_accuracy_pct" in self.last_eval:
            acc = f" | ความแม่นยำ {self.last_eval['map_accuracy_pct']}%"
        if self.robot:
            kind_txt = "ซิม (SIM)" if self.robot_kind == "sim" else "หุ่นจริง (REAL)"
            pos = f" | [{kind_txt}] ช่อง {self.robot.cell} หัน {DIRS[self.robot.heading]}"
        else:
            pos = " | (ตัดการเชื่อมต่อ)"
        state = " | [กำลังทำงาน]" if self.busy() else ""
        self.status.set(f"{m.w}x{m.h} | สำรวจแล้ว {vis}/{tot} ({100*vis/tot:.0f}%){acc}{pos}{state}")

    def _draw_edge(self, g, x, y, d, mode):
        if d == 0: a, b = self._px(x, y + 1), self._px(x + 1, y + 1)
        elif d == 2: a, b = self._px(x, y), self._px(x + 1, y)
        elif d == 1: a, b = self._px(x + 1, y), self._px(x + 1, y + 1)
        else: a, b = self._px(x, y), self._px(x, y + 1)
        st = g.state(x, y, d)
        wrong = (mode != "gt" and self.v_showgt.get() and self.gt is not None
                 and (self.gt.w, self.gt.h) == (g.w, g.h) and self.gt.state(x, y, d) != st)
        if st == WALL:
            self.cv.create_line(*a, *b, fill="#FF5252" if wrong else "#64B5F6", width=7, capstyle=tk.ROUND)
        elif st == UNKNOWN:
            self.cv.create_line(*a, *b, fill="#FFB300", width=2, dash=(4, 4))
        elif wrong:
            self.cv.create_line(*a, *b, fill="#FF5252", width=3, dash=(2, 3))
        if mode != "gt" and self.v_showgt.get() and self.gt is not None and \
                (self.gt.w, self.gt.h) == (g.w, g.h) and self.gt.state(x, y, d) == WALL and st != WALL:
            self.cv.create_line(*a, *b, fill="#90A4AE", width=3)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.mainloop()

    def _close(self):
        self.stop_event.set()
        try:
            if self.robot: self.robot.close()
            if self.logger: self.logger.close()
        finally:
            try: self._session_log_file.close()
            except: pass
            self.root.destroy()

if __name__ == "__main__":
    App().run()