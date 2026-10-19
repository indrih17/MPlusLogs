"""Companion-owned, non-activating popup cards on the foreground monitor."""
from collections import deque
import ctypes
from ctypes import wintypes as wt
from pathlib import Path
import time
import tkinter as tk

import appearance


def show_without_activation(window):
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetParent.argtypes=[wt.HWND];user.GetParent.restype=wt.HWND
    user.GetWindowLongPtrW.argtypes=[wt.HWND,ctypes.c_int];user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    user.SetWindowLongPtrW.argtypes=[wt.HWND,ctypes.c_int,ctypes.c_ssize_t];user.SetWindowLongPtrW.restype=ctypes.c_ssize_t
    user.SetWindowPos.argtypes=[wt.HWND,wt.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wt.UINT]
    user.GetForegroundWindow.restype=wt.HWND
    user.MonitorFromWindow.argtypes=[wt.HWND,wt.DWORD];user.MonitorFromWindow.restype=wt.HANDLE
    class MonitorInfo(ctypes.Structure):
        _fields_=[('size',wt.DWORD),('monitor',wt.RECT),('work',wt.RECT),('flags',wt.DWORD)]
    user.GetMonitorInfoW.argtypes=[wt.HANDLE,ctypes.POINTER(MonitorInfo)]
    info=MonitorInfo();info.size=ctypes.sizeof(info)
    monitor=user.MonitorFromWindow(user.GetForegroundWindow(),2)
    if not user.GetMonitorInfoW(monitor,ctypes.byref(info)):raise ctypes.WinError(ctypes.get_last_error())
    hwnd=user.GetParent(window.winfo_id()) or window.winfo_id()
    style=user.GetWindowLongPtrW(hwnd,-20)
    # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW. Applied before mapping, so the
    # card cannot activate its hidden owner or interrupt keyboard input.
    user.SetWindowLongPtrW(hwnd,-20,style | 0x08000000 | 0x80)
    window.deiconify()
    width,height=window.winfo_reqwidth(),window.winfo_reqheight()
    x=max(info.work.left,info.work.right-width-16)
    y=max(info.work.top,info.work.bottom-height-16)
    if not user.SetWindowPos(hwnd,wt.HWND(-1),x,y,width,height,0x10 | 0x40):
        raise ctypes.WinError(ctypes.get_last_error())


class PopupNotifications:
    def __init__(self,root,on_click,theme=lambda:'light',duration=8000):
        self.root,self.on_click,self.theme,self.duration=root,on_click,theme,duration
        self.window=None
        self.timer=None
        self.pending=deque(maxlen=3)
        self.current=None
        self.status=None
        self.hovered=False

    def show(self,title,text):
        item=(title,text)
        if self.window is not None:
            if item==self.current:self._schedule()
            elif item not in self.pending:self.pending.append(item)
            return
        try:
            self._create_card(title,text)
        except Exception:
            self.close()
            raise
        self.current=item
        self.status={'backend':'companion','state':'shown','time':time.time()}
        self._schedule()

    def _create_card(self,title,text):
        palette=appearance.PALETTES.get(self.theme(),appearance.PALETTES['light'])
        window=self.window=tk.Toplevel(self.root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes('-topmost',True)
        window.configure(bg=palette['border'])
        window.title('MPlusLogs Companion notification')
        card=tk.Frame(window,bg=palette['background'],padx=16,pady=14)
        card.pack(fill='both',expand=True,padx=1,pady=1)
        image=tk.PhotoImage(master=window,file=str(Path(__file__).with_name('assets')/'mpluslogs.png')).subsample(8,8)
        window.notification_icon=image
        icon=tk.Label(card,image=image,bg=palette['background'])
        icon.grid(row=0,column=0,rowspan=2,padx=(0,12),sticky='n')
        heading=tk.Label(card,text=title,font=('Segoe UI',10,'bold'),fg=palette['text'],bg=palette['background'],anchor='w')
        heading.grid(row=0,column=1,sticky='w')
        body=tk.Label(card,text=text,font=('Segoe UI',10),fg=palette['muted'],bg=palette['background'],
                      wraplength=300,justify='left',anchor='w')
        body.grid(row=1,column=1,sticky='w',pady=(4,0))
        close=tk.Label(card,text='×',font=('Segoe UI',15),fg=palette['muted'],bg=palette['background'],cursor='hand2')
        close.grid(row=0,column=2,padx=(14,0),sticky='ne')
        close.bind('<Button-1>',lambda event:self._dismiss())
        for widget in (card,icon,heading,body):
            widget.configure(cursor='hand2')
            widget.bind('<Button-1>',lambda event:self._activate())
        window.bind('<Enter>',lambda event:self._enter())
        window.bind('<Leave>',lambda event:self._leave())
        window.update_idletasks()
        show_without_activation(window)

    def _enter(self):
        self.hovered=True
        self._cancel_timer()

    def _leave(self):
        if self.window is not None:
            x,y=self.window.winfo_pointerxy()
            left,top=self.window.winfo_rootx(),self.window.winfo_rooty()
            if left<=x<left+self.window.winfo_width() and top<=y<top+self.window.winfo_height():return
        self.hovered=False
        self._schedule()

    def _cancel_timer(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer=None

    def _schedule(self):
        self._cancel_timer()
        if self.window is not None and not self.hovered:self.timer=self.root.after(self.duration,self._dismiss)

    def _dismiss(self):
        self._cancel_timer()
        window,self.window=self.window,None
        self.current=None
        self.hovered=False
        if window is not None:window.destroy()
        self.status={'backend':'companion','state':'closed','time':time.time()}
        if self.pending:
            title,text=self.pending.popleft()
            self.show(title,text)

    def _activate(self):
        self.close()
        self.on_click()

    def close(self):
        self.pending.clear()
        self._dismiss()
