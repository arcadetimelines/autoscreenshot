import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import xml.etree.ElementTree as ET

import os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE, "batch.txt")

CHECKED = "\u2611"    # ☑
UNCHECKED = "\u2610"  # ☐


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Machine picker")
        self.geometry("900x500")

        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=8, pady=8)
        self.status = ttk.Label(self, anchor="w", relief="sunken", padding=(6, 2))
        self.status.pack(side="bottom", fill="x")
        frame = ttk.Frame(self)
        frame.pack(side="top", fill="both", expand=True)

        columns = ("description", "year", "manufacturer")
        self.tree = ttk.Treeview(frame, columns=columns, selectmode="none")
        self.titles = {"#0": "Name", "description": "Description",
                       "year": "Year", "manufacturer": "Manufacturer"}
        self.sort_state = {}  # column -> last used reverse flag
        for col, title in self.titles.items():
            self.tree.heading(col, text=title,
                              command=lambda c=col: self.sort_by(c))
        self.tree.column("#0", width=180)
        self.tree.column("description", width=380)
        self.tree.column("year", width=70, anchor="center")
        self.tree.column("manufacturer", width=200)

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        row1 = ttk.Frame(bar)
        row1.pack(side="top", fill="x")
        search_row = ttk.Frame(bar)
        search_row.pack(side="top", fill="x", pady=(8, 0))
        row2 = ttk.Frame(bar)
        row2.pack(side="top", fill="x", pady=(8, 0))

        # Search row: field to search in + text to search for
        ttk.Label(search_row, text="Search in:").pack(side="left")
        self.search_field = ttk.Combobox(
            search_row, state="readonly", width=14,
            values=("Name", "Description", "Year", "Manufacturer"))
        self.search_field.current(0)
        self.search_field.pack(side="left", padx=4)
        self.search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=self.search_var,
                  width=40).pack(side="left", padx=4)
        ttk.Button(search_row, text="Search and select",
                   command=self.run_search).pack(side="left")

        # Row 1: selection and expand/collapse buttons
        ttk.Button(row1, text="Select all",
                   command=lambda: self.set_all(True)).pack(side="left")
        ttk.Button(row1, text="Select none",
                   command=lambda: self.set_all(False)).pack(side="left", padx=4)
        ttk.Button(row1, text="Select only parents",
                   command=self.select_only_parents).pack(side="left")
        ttk.Button(row1, text="Select only clones",
                   command=self.select_only_clones).pack(side="left", padx=4)
        ttk.Button(row1, text="Expand all",
                   command=lambda: self.set_open(True)).pack(side="left", padx=(12, 4))
        ttk.Button(row1, text="Collapse all",
                   command=lambda: self.set_open(False)).pack(side="left")

        # Row 2: emulator choice and batch file
        self.emulator = tk.StringVar(value="mame")
        ttk.Radiobutton(row2, text="mame", value="mame",
                        variable=self.emulator).pack(side="left", padx=(0, 4))
        ttk.Radiobutton(row2, text="hbmame", value="hbmame",
                        variable=self.emulator).pack(side="left", padx=(0, 12))
        ttk.Button(row2, text="Write Batch file",
                   command=self.write_selected).pack(side="left")

        self.names = {}   # item id -> machine name
        self.checked = {} # item id -> bool

        self.tree.bind("<Button-1>", self.on_click)
        self.tree.bind("<space>", self.on_space)

        # Ask for the XML file once the window is up
        self.after(100, self.load_xml)

    def load_xml(self):
        path = filedialog.askopenfilename(
            parent=self, title="Choose an XML file", initialdir=BASE,
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")])
        if not path:
            self.destroy()
            return
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as e:
            messagebox.showerror("Error", f"Could not read {path}:\n{e}")
            self.destroy()
            return
        build = root.get("build")
        if build:
            self.title(f"Machine picker - {build}")

        # Skip BIOS and device entries
        machines = [m for m in root.iter("machine")
                    if m.get("isbios") != "yes" and m.get("isdevice") != "yes"]
        all_names = {m.get("name", "") for m in machines}
        iid_by_name = {}  # machine name -> treeview item id

        def add(m, parent_iid):
            name = m.get("name", "")
            vals = tuple((m.findtext(t) or "").strip()
                         for t in ("description", "year", "manufacturer"))
            iid = self.tree.insert(parent_iid, "end",
                                   text=f"{UNCHECKED} {name}", values=vals)
            self.names[iid] = name
            self.checked[iid] = False
            iid_by_name[name] = iid

        # Machines without a (known) parent go at the top level first
        pending = []
        for m in machines:
            parent = m.get("cloneof")
            if parent and parent in all_names and parent != m.get("name"):
                pending.append(m)
            else:
                add(m, "")

        # Then add clones under their parent (repeat to handle clones of clones)
        while pending:
            remaining = []
            for m in pending:
                parent_iid = iid_by_name.get(m.get("cloneof"))
                if parent_iid:
                    add(m, parent_iid)
                else:
                    remaining.append(m)
            if len(remaining) == len(pending):  # unresolved -> top level
                for m in remaining:
                    add(m, "")
                break
            pending = remaining

        self.update_status()

    def set_open(self, state):
        for iid in self.all_items():
            if self.tree.get_children(iid):
                self.tree.item(iid, open=state)

    def run_search(self, *_):
        """Check every entry that matches the search text in the chosen field.
        Entries that don't match are left as they are."""
        text = self.search_var.get().strip().lower()
        if not text:
            return
        column = {"Name": "#0", "Description": "description",
                  "Year": "year", "Manufacturer": "manufacturer"}[self.search_field.get()]

        found = 0
        for iid in self.names:
            value = self.names[iid] if column == "#0" else self.tree.set(iid, column)
            if text in value.lower():
                found += 1
                self.checked[iid] = True
                self.tree.item(iid, text=f"{CHECKED} {self.names[iid]}")
                # Make matching clones visible by opening their parents
                parent = self.tree.parent(iid)
                while parent:
                    self.tree.item(parent, open=True)
                    parent = self.tree.parent(parent)

        self.update_status()
        if not found:
            messagebox.showinfo("Search", "No entries found.")

    def select_where(self, predicate):
        """Set every checkbox according to predicate(iid)."""
        for iid in self.names:
            state = bool(predicate(iid))
            self.checked[iid] = state
            self.tree.item(iid, text=f"{CHECKED if state else UNCHECKED} {self.names[iid]}")
        self.update_status()

    def select_only_parents(self):
        """Check every top-level (parent) entry and uncheck all clones."""
        self.select_where(lambda iid: self.tree.parent(iid) == "")

    def select_only_clones(self):
        """Check every clone and uncheck all parents."""
        self.select_where(lambda iid: self.tree.parent(iid) != "")

    def update_status(self):
        parents = [i for i in self.names if self.tree.parent(i) == ""]
        clones = [i for i in self.names if self.tree.parent(i) != ""]
        sel_p = sum(self.checked[i] for i in parents)
        sel_c = sum(self.checked[i] for i in clones)
        self.status.config(
            text=f"Parents: {len(parents)}   Clones: {len(clones)}   |   "
                 f"Selected parents: {sel_p}   Selected clones: {sel_c}")

    def all_items(self, parent=""):
        """All item ids in display order, including children."""
        for iid in self.tree.get_children(parent):
            yield iid
            yield from self.all_items(iid)

    def sort_key(self, col, iid):
        value = self.names[iid] if col == "#0" else self.tree.set(iid, col)
        value = value.strip()
        # numbers sort before text, and numerically (e.g. year)
        try:
            return (0, int(value), "")
        except ValueError:
            return (1, 0, value.lower())

    def sort_by(self, col):
        reverse = not self.sort_state.get(col, True)  # first click = ascending
        def sort_children(parent):
            items = list(self.tree.get_children(parent))
            items.sort(key=lambda i: self.sort_key(col, i), reverse=reverse)
            for index, iid in enumerate(items):
                self.tree.move(iid, parent, index)
                sort_children(iid)

        sort_children("")
        self.sort_state = {col: reverse}
        for c, title in self.titles.items():
            arrow = ""
            if c == col:
                arrow = " \u25bc" if reverse else " \u25b2"
            self.tree.heading(c, text=title + arrow)

    def toggle(self, iid):
        state = not self.checked[iid]
        self.checked[iid] = state
        self.tree.item(iid, text=f"{CHECKED if state else UNCHECKED} {self.names[iid]}")
        self.update_status()

    def on_click(self, event):
        # Ignore clicks on the expand/collapse arrow
        if "indicator" in self.tree.identify("element", event.x, event.y):
            return
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_column(event.x) == "#0":
            self.toggle(iid)
            self.tree.focus(iid)

    def on_space(self, event):
        iid = self.tree.focus()
        if iid:
            self.toggle(iid)

    def set_all(self, state):
        self.select_where(lambda iid: state)

    def write_selected(self):
        emu = self.emulator.get()
        selected = [
            f"{emu} {self.names[i]} -skip_gameinfo -autoboot_script autoscreenshot.lua"
            for i in self.all_items() if self.checked[i]
        ]
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(selected) + ("\n" if selected else ""))
        messagebox.showinfo("Done", f"Wrote {len(selected)} name(s) to {OUT_FILE}")


if __name__ == "__main__":
    App().mainloop()
