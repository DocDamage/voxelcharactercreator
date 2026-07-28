from __future__ import annotations
import json, os, queue, shutil, subprocess, threading, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.llm_client import run_ollama, run_openai, apply_patch
from services.job_validator import validate_job

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / 'config' / 'settings.json'

def load_settings():
    try: return json.loads(SETTINGS.read_text(encoding='utf-8'))
    except Exception: return {'blender_path':'','render_resolution':768}

def save_settings(data): SETTINGS.write_text(json.dumps(data, indent=2), encoding='utf-8')

def detect_blender():
    candidates=[shutil.which('blender')]
    base=Path(r'C:\Program Files\Blender Foundation')
    if base.exists(): candidates += [str(p) for p in sorted(base.glob('Blender */blender.exe'), reverse=True)]
    for p in candidates:
        if p and Path(p).exists(): return str(Path(p))
    return ''

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Voxel Character Factory'); self.geometry('1080x700'); self.minsize(900,580)
        self.settings=load_settings(); self.settings['blender_path']=self.settings.get('blender_path') or detect_blender()
        self.jobs=sorted((ROOT/'characters').glob('*/*.json')); self.q=queue.Queue(); self.proc=None
        self.columnconfigure(1,weight=1); self.rowconfigure(0,weight=1)
        left=ttk.Frame(self,padding=12); left.grid(row=0,column=0,sticky='ns')
        ttk.Label(left,text='Pilot Cast',font=('Segoe UI',16,'bold')).pack(anchor='w')
        self.list=tk.Listbox(left,width=29,height=25,exportselection=False); self.list.pack(fill='y',expand=True,pady=10)
        for p in self.jobs:
            d=json.loads(p.read_text(encoding='utf-8')); self.list.insert(tk.END,f"{d['game'].upper()}  •  {d['name']}")
        self.list.bind('<<ListboxSelect>>',lambda e:self.show_job())
        for label,cmd in [('Build Character',self.build_one),('Build All',self.build_all),('Open Exports',self.open_exports),('Settings',self.open_settings)]:
            ttk.Button(left,text=label,command=cmd).pack(fill='x',pady=3)
        main=ttk.Frame(self,padding=12); main.grid(row=0,column=1,sticky='nsew'); main.columnconfigure(0,weight=1); main.rowconfigure(1,weight=1)
        ttk.Label(main,text='Character Job',font=('Segoe UI',16,'bold')).grid(row=0,column=0,sticky='w')
        self.editor=tk.Text(main,wrap='none',font=('Consolas',10)); self.editor.grid(row=1,column=0,sticky='nsew',pady=(10,8))
        ttk.Button(main,text='Save Job Changes',command=self.save_job).grid(row=2,column=0,sticky='e')
        box=ttk.LabelFrame(main,text='Build Log',padding=8); box.grid(row=3,column=0,sticky='nsew',pady=(12,0)); box.columnconfigure(0,weight=1)
        self.log=tk.Text(box,height=11,bg='#111',fg='#eee',insertbackground='white',font=('Consolas',9)); self.log.grid(row=0,column=0,sticky='nsew')
        self.bar=ttk.Progressbar(box,mode='indeterminate'); self.bar.grid(row=1,column=0,sticky='ew',pady=(8,0))
        if self.jobs: self.list.selection_set(0); self.show_job()
        self.after(100,self.drain)
    def selected(self):
        s=self.list.curselection(); return self.jobs[s[0]] if s else None
    def show_job(self):
        p=self.selected();
        if p: self.editor.delete('1.0',tk.END); self.editor.insert('1.0',p.read_text(encoding='utf-8'))
    def save_job(self):
        p=self.selected();
        if not p:return
        try: d=json.loads(self.editor.get('1.0',tk.END)); p.write_text(json.dumps(d,indent=2),encoding='utf-8'); messagebox.showinfo('Saved',d.get('name',p.stem))
        except Exception as e: messagebox.showerror('Invalid job',str(e))
    def build_one(self):
        p=self.selected();
        if p:self.start([p])
    def build_all(self): self.start(self.jobs)
    def start(self,jobs):
        if self.proc: return messagebox.showwarning('Busy','A build is already running.')
        blender=self.settings.get('blender_path') or detect_blender()
        if not blender or not Path(blender).exists(): return messagebox.showerror('Blender not found','Open Settings and select blender.exe.')
        self.settings['blender_path']=blender; save_settings(self.settings); self.bar.start(10)
        threading.Thread(target=self.worker,args=(jobs,),daemon=True).start()
    def worker(self,jobs):
        try:
            for i,p in enumerate(jobs,1):
                self.q.put(f'\n=== [{i}/{len(jobs)}] {p.stem} ===\n')
                cmd=[self.settings['blender_path'],'--background','--python',str(ROOT/'blender_worker/process_character.py'),'--','--job',str(p),'--project-root',str(ROOT)]
                flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
                self.proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',cwd=ROOT,creationflags=flags)
                for line in self.proc.stdout:self.q.put(line)
                code=self.proc.wait()
                if code: raise RuntimeError(f'Blender exited with code {code}')
            self.q.put('__DONE__')
        except Exception as e:self.q.put('__FAIL__'+str(e))
        finally:self.proc=None
    def drain(self):
        try:
            while True:
                t=self.q.get_nowait()
                if t=='__DONE__': self.bar.stop(); messagebox.showinfo('Complete','Builds completed.'); t='\nBuilds completed.\n'
                elif t.startswith('__FAIL__'): self.bar.stop(); messagebox.showerror('Failed',t[8:]); t='\nFAILED: '+t[8:]+'\n'
                self.log.insert(tk.END,t); self.log.see(tk.END)
        except queue.Empty: pass
        self.after(100,self.drain)
    def open_exports(self):
        p=ROOT/'exports'; p.mkdir(exist_ok=True)
        if os.name=='nt': os.startfile(p)
        else: subprocess.Popen(['xdg-open',str(p)])
    def open_settings(self):
        w=tk.Toplevel(self); w.title('Settings'); w.geometry('760x170'); w.transient(self); w.grab_set()
        ttk.Label(w,text='Blender executable').pack(anchor='w',padx=12,pady=(12,4)); v=tk.StringVar(value=self.settings.get('blender_path',''))
        row=ttk.Frame(w); row.pack(fill='x',padx=12); ttk.Entry(row,textvariable=v).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Browse',command=lambda: v.set(filedialog.askopenfilename(filetypes=[('Blender','blender.exe'),('Executable','*.exe'),('All','*.*')]) or v.get())).pack(side='left',padx=(8,0))
        def commit(): self.settings['blender_path']=v.get().strip(); save_settings(self.settings); w.destroy()
        ttk.Button(w,text='Save',command=commit).pack(anchor='e',padx=12,pady=18)
if __name__=='__main__': App().mainloop()
    def describe_changes(self) -> None:
        path = self.selected_job()
        if not path:
            return
        provider = self.settings.get("llm_provider", "none")
        if provider == "none":
            messagebox.showinfo("LLM disabled", "Set llm_provider to ollama or openai in config/settings.json.")
            return
        prompt = simpledialog.askstring("Describe Changes", "Describe what should change in this character job:")
        if not prompt:
            return
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if provider == "ollama":
                patch = run_ollama(prompt, self.settings["ollama_base_url"], self.settings["ollama_model"])
            else:
                patch = run_openai(prompt, self.settings["openai_base_url"], self.settings["openai_model"])
            updated = apply_patch(job, patch)
            errors = validate_job(updated)
            if errors:
                raise RuntimeError("\n".join(errors))
            path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
            self._show_job()
            messagebox.showinfo("Job updated", "The character job was updated and validated.")
        except Exception as exc:
            messagebox.showerror("LLM update failed", str(exc))


