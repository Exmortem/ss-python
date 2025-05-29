import socket
import cv2
import numpy as np
import mss
import mss.tools
import threading
import time
from zeroconf import ServiceInfo, Zeroconf
import tkinter as tk
from tkinter import ttk
import queue
import atexit
import subprocess
import os
import asyncio
import struct
import psutil
import signal
import json
from pynput import keyboard
import keyboard as keyboard_lib  # NEW: Import keyboard library for robust key simulation

# Control Port offset - Should match client
CONTROL_PORT_OFFSET = 1
HOST_CONFIG_FILE = "host_config.json" # Config file name
DEFAULT_PORT = 8485
# Mapping from Tkinter keysyms to pynput Keys (add more as needed)
SPECIAL_KEYS = {
    # Modifiers
    'Shift_L': keyboard.Key.shift_l,
    'Shift_R': keyboard.Key.shift_r,
    'Control_L': keyboard.Key.ctrl_l,
    'Control_R': keyboard.Key.ctrl_r,
    'Alt_L': keyboard.Key.alt_l,
    'Alt_R': keyboard.Key.alt_r,
    'Super_L': keyboard.Key.cmd_l, # Windows/Command key Left
    'Super_R': keyboard.Key.cmd_r, # Windows/Command key Right
    'Caps_Lock': keyboard.Key.caps_lock,
    'Num_Lock': keyboard.Key.num_lock,
    'Scroll_Lock': keyboard.Key.scroll_lock,
    
    # Whitespace/Editing
    'Tab': keyboard.Key.tab,
    'ISO_Left_Tab': keyboard.Key.tab, # Shift+Tab often produces this
    'Return': keyboard.Key.enter, # Enter key
    'KP_Enter': keyboard.Key.enter, # Numpad Enter (assuming distinct keysym)
    'space': keyboard.Key.space,
    'Escape': keyboard.Key.esc,
    'BackSpace': keyboard.Key.backspace,
    'Delete': keyboard.Key.delete,
    'KP_Delete': keyboard.Key.delete, # If KP_Decimal acts as Delete
    'Insert': keyboard.Key.insert,
    'KP_Insert': keyboard.Key.insert, # If KP_0 acts as Insert
    
    # Navigation
    'Home': keyboard.Key.home,
    'KP_Home': keyboard.Key.home,    # If KP_7 acts as Home
    'End': keyboard.Key.end,
    'KP_End': keyboard.Key.end,     # If KP_1 acts as End
    'Prior': keyboard.Key.page_up, # Page Up
    'KP_Prior': keyboard.Key.page_up, # If KP_9 acts as Page Up
    'Next': keyboard.Key.page_down, # Page Down (Tkinter keysym for PgDn)
    'KP_Next': keyboard.Key.page_down, # If KP_3 acts as Page Down
    'Up': keyboard.Key.up,
    'KP_Up': keyboard.Key.up,       # If KP_8 acts as Up
    'Down': keyboard.Key.down,
    'KP_Down': keyboard.Key.down,    # If KP_2 acts as Down
    'Left': keyboard.Key.left,
    'KP_Left': keyboard.Key.left,    # If KP_4 acts as Left
    'Right': keyboard.Key.right,
    'KP_Right': keyboard.Key.right,   # If KP_6 acts as Right
    'KP_Begin': None, # Map to None as pynput Key.clear doesn't exist and behavior is ambiguous
    
    # Function keys (F1-F20)
    'F1': keyboard.Key.f1,
    'F2': keyboard.Key.f2,
    'F3': keyboard.Key.f3,
    'F4': keyboard.Key.f4,
    'F5': keyboard.Key.f5,
    'F6': keyboard.Key.f6,
    'F7': keyboard.Key.f7,
    'F8': keyboard.Key.f8,
    'F9': keyboard.Key.f9,
    'F10': keyboard.Key.f10,
    'F11': keyboard.Key.f11,
    'F12': keyboard.Key.f12,
    'F13': keyboard.Key.f13,
    'F14': keyboard.Key.f14,
    'F15': keyboard.Key.f15,
    'F16': keyboard.Key.f16,
    'F17': keyboard.Key.f17,
    'F18': keyboard.Key.f18,
    'F19': keyboard.Key.f19,
    'F20': keyboard.Key.f20,

    # Numpad Operators/Misc (assuming distinct keysyms)
    'KP_Add': '+',
    'KP_Subtract': '-',
    'KP_Multiply': '*',
    'KP_Divide': '/',
    'KP_Decimal': '.',
    'KP_Separator': '.', # Often same as decimal
    
    # Other Keys
    'Print': keyboard.Key.print_screen,
    'Pause': keyboard.Key.pause,
    'Menu': keyboard.Key.menu,
    
    # --- Additional Keys Added ---
    'Select': None, # Removed as Key.select doesn't exist in pynput
    'Execute': None, # Removed as Key.execute doesn't exist in pynput
    'Help': None, # Removed as Key.help doesn't exist in pynput
    'Sleep': None, # Removed as Key.sleep doesn't exist in pynput
    'F21': keyboard.Key.f21,
    'F22': keyboard.Key.f22,
    'F23': keyboard.Key.f23,
    'F24': keyboard.Key.f24,
    # Browser (Keysyms might vary - pynput doesn't have direct Key constants)
    'Back': None,
    'Browser_Back': None,
    'Forward': None,
    'Browser_Forward': None,
    'Refresh': None,
    'Browser_Refresh': None,
    'Stop': None,
    'Browser_Stop': None,
    'Search': None,
    'Browser_Search': None,
    'Favorites': None,
    'Browser_Favorites': None,
    'HomePage': None,
    'Browser_Home': None,
    # Media (Keysyms might vary - pynput doesn't have direct Key constants)
    'AudioMute': None,
    'Volume_Mute': None,
    'AudioLowerVolume': None,
    'Volume_Down': None,
    'AudioRaiseVolume': None,
    'Volume_Up': None,
    'AudioNext': None,
    'Media_Next': None,
    'AudioPrev': None,
    'Media_Prev': None,
    'AudioStop': None,
    'Media_Stop': None,
    'AudioPlay': None,
    'Media_Play_Pause': None,
    # Launch (Keysyms might vary - pynput doesn't have direct Key constants)
    'LaunchMail': None,
    'Mail': None,
    'LaunchMedia': None,
    'Media': None,
    'Launch0': None,
    'LaunchA': None,
    'Launch1': None,
    'LaunchB': None,
    # --- End Added Keys ---
}

# --- NEW: Keycode mapping for Windows --- 
# Maps Windows keycodes received from client Tkinter event.keycode
# to pynput KeyCode objects using Windows Virtual Key (VK) codes.
# VK codes often match Tkinter keycodes for Numpad on Windows.
KEYCODE_MAP = {
    # Numpad Numbers (VK_NUMPAD0 to VK_NUMPAD9 are 96 to 105)
    96: keyboard.KeyCode.from_vk(96),  # Numpad 0
    97: keyboard.KeyCode.from_vk(97),  # Numpad 1
    98: keyboard.KeyCode.from_vk(98),  # Numpad 2
    99: keyboard.KeyCode.from_vk(99),  # Numpad 3
    100: keyboard.KeyCode.from_vk(100), # Numpad 4
    101: keyboard.KeyCode.from_vk(101), # Numpad 5
    102: keyboard.KeyCode.from_vk(102), # Numpad 6
    103: keyboard.KeyCode.from_vk(103), # Numpad 7
    104: keyboard.KeyCode.from_vk(104), # Numpad 8
    105: keyboard.KeyCode.from_vk(105), # Numpad 9
    
    # Numpad Operators (VK codes)
    106: keyboard.KeyCode.from_vk(106), # Numpad * (Multiply)
    107: keyboard.KeyCode.from_vk(107), # Numpad + (Add)
    # Separator (VK 108) - often handled differently, might not map well
    109: keyboard.KeyCode.from_vk(109), # Numpad - (Subtract)
    110: keyboard.KeyCode.from_vk(110), # Numpad . (Decimal)
    111: keyboard.KeyCode.from_vk(111), # Numpad / (Divide)
    
    # We can add more specific keycode mappings here if needed
    # e.g., for KP_Enter if its keycode is distinct and needed
}
# --- END NEW --- 

def get_sim_key(keycode, char):
    """Returns the key to simulate based on keycode and char."""
    # Priority 1: Use KEYCODE_MAP for special keys (numpad, function, etc.)
    if keycode in KEYCODE_MAP:
        return KEYCODE_MAP[keycode]
    # Priority 2: Use char for printable characters
    elif char and len(char) == 1 and char != ' ':
        return char
    # Priority 3: Space
    elif char == ' ':
        return ' '
    # Priority 4: Unmapped
    else:
        print(f"[Control] Warning: Unmapped key event: keycode={keycode}, char='{char}'")
        return None

def kill_process_on_port(port):
    """Kill any process using the specified port"""
    try:
        if os.name == 'nt':  # Windows
            # Find process using the port
            cmd = f'netstat -ano | findstr :{port}'
            result = subprocess.check_output(cmd, shell=True).decode()
            if result:
                # Extract PID from the result
                pid = result.strip().split()[-1]
                # Kill the process
                subprocess.run(f'taskkill /F /PID {pid}', shell=True)
                return True
        else:  # Linux/Mac
            # Find process using the port
            cmd = f'lsof -i :{port} -t'
            pid = subprocess.check_output(cmd, shell=True).decode().strip()
            if pid:
                # Kill the process
                subprocess.run(f'kill -9 {pid}', shell=True)
                return True
    except:
        pass
    return False

def is_port_in_use(port):
    """Check if a port is in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_local_ip():
    """Get the local IP address of the machine"""
    try:
        # Create a temporary socket to get the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"Detected local IP: {local_ip}")
        return local_ip
    except:
        print("Could not determine external IP address, falling back to 127.0.0.1")
        return "127.0.0.1"  # Fallback to localhost

def get_all_local_ips():
    """Get all local IP addresses of the machine"""
    ips = []
    try:
        # Get all network interfaces
        addrs = socket.getaddrinfo(socket.gethostname(), None)
        for addr in addrs:
            ip = addr[4][0]
            # Only add IPv4 addresses and skip localhost
            if '.' in ip and ip != '127.0.0.1':
                ips.append(ip)
        
        # If no IPs found, try the primary method
        if not ips:
            primary_ip = get_local_ip()
            if primary_ip != '127.0.0.1':
                ips.append(primary_ip)
                
        # Remove duplicates
        ips = list(set(ips))
        print(f"All detected local IPs: {ips}")
    except Exception as e:
        print(f"Error getting local IPs: {e}")
    
    # If still no IPs, add loopback
    if not ips:
        ips.append('127.0.0.1')
        
    return ips

class ScreenShareHost:
    def __init__(self, host='0.0.0.0'): # Remove default port from here
        self.host = host
        # Port will be set after loading settings
        self.port = DEFAULT_PORT 
        self.control_port = self.port + CONTROL_PORT_OFFSET 
        self.running = False
        self.sct = mss.mss()
        self.clients = []
        self.status_queue = queue.Queue()
        self.server_socket = None
        self.control_server_socket = None
        
        # Get both primary IP and all available IPs
        self.host_ip = get_local_ip()
        self.all_ips = get_all_local_ips()
        print(f"Primary IP: {self.host_ip}, All IPs: {self.all_ips}")
        
        self.zeroconf = Zeroconf()
        self.service_info = None
        self.client_threads = []
        self.control_threads = []
        self.keyboard_controller = keyboard.Controller()
        
        # --- Load Initial Settings FIRST ---
        loaded_settings = self.load_settings()
        # --- End Load ---

        # --- Set Ports from Settings --- 
        self.port = loaded_settings.get('port', DEFAULT_PORT)
        self.control_port = self.port + CONTROL_PORT_OFFSET
        print(f"Using Port: {self.port} (Control: {self.control_port})")
        # --- End Set Ports ---
        
        # --- Create Root Window SECOND ---
        self.root = tk.Tk()
        self.root.title("Screen Share Host")
        
        # --- Create Tkinter Vars THIRD (using loaded values) ---
        self.capture_width = tk.IntVar(value=loaded_settings.get('width', 500))
        self.capture_height = tk.IntVar(value=loaded_settings.get('height', 500))
        self.capture_fps = tk.IntVar(value=loaded_settings.get('fps', 60))
        self.fidelity_var = tk.StringVar(value=loaded_settings.get('fidelity', 'JPEG'))
        self.port_var = tk.IntVar(value=self.port) # Use the loaded/default port
        # --- End Create Vars ---
        
        # --- Port Checks FOURTH (Using self.port / self.control_port) ---
        # Check and kill any process using the stream port
        if is_port_in_use(self.port):
            print(f"Stream port {self.port} is in use. Attempting to kill process...")
            if kill_process_on_port(self.port):
                print(f"Successfully killed process using port {self.port}")
                # Add a small delay to allow the OS to release the port
                time.sleep(0.5)
            else:
                print(f"Warning: Failed to kill process using stream port {self.port}. Binding might fail.")
        
        # Check and kill any process using the control port
        if is_port_in_use(self.control_port):
            print(f"Control port {self.control_port} is in use. Attempting to kill process...")
            if kill_process_on_port(self.control_port):
                print(f"Successfully killed process using control port {self.control_port}")
                time.sleep(0.5)
            else:
                print(f"Warning: Failed to kill process using control port {self.control_port}. Binding might fail.")
                # Decide if this is fatal? For now, just warn.
                # return # Or raise an exception?
        # --- End Port Checks ---

        # --- Defer Socket and Zeroconf Setup to start() --- 
        self.server_socket = None
        self.control_server_socket = None
        # --- End Defer --- 
        
        # Setup UI LAST (needs root and tk vars)
        self.setup_ui()
        
        # Register cleanup function
        atexit.register(self.cleanup)
        
    def load_settings(self):
        """Load settings (dimensions, FPS, fidelity, port) from config file."""
        defaults = {
            'width': 500, 'height': 500, 'fps': 60, 
            'fidelity': 'JPEG', 'port': DEFAULT_PORT
        }
        settings = defaults.copy()
        
        try:
            if os.path.exists(HOST_CONFIG_FILE):
                with open(HOST_CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    
                    # Validate and load each setting
                    w = config.get('capture_width', defaults['width'])
                    h = config.get('capture_height', defaults['height'])
                    f = config.get('capture_fps', defaults['fps'])
                    fid = config.get('fidelity', defaults['fidelity']).upper()
                    p = config.get('port', defaults['port'])
                    
                    valid_numeric = True
                    if not isinstance(w, int) or w <= 0: valid_numeric = False
                    if not isinstance(h, int) or h <= 0: valid_numeric = False
                    if not isinstance(f, int) or f <= 0: valid_numeric = False
                    # Validate Port (basic range check)
                    if not isinstance(p, int) or p <= 1023 or p > 65535:
                         print(f"Warning: Invalid port {p} in config, using default {defaults['port']}.")
                         p = defaults['port']
                         # Don't mark as invalid overall, just use default port
                    
                    # Validate Fidelity
                    if fid not in ['JPEG', 'PNG']:
                         print(f"Warning: Invalid fidelity '{fid}' in config, defaulting to JPEG.")
                         fid = defaults['fidelity']
                    
                    if valid_numeric:
                         settings['width'] = w
                         settings['height'] = h
                         settings['fps'] = f
                         settings['fidelity'] = fid
                         settings['port'] = p # Store validated/defaulted port
                         print(f"Loaded settings: {w}x{h} @ {f} FPS, Fidelity: {fid}, Port: {p}")
                    else:
                         print("Warning: Invalid numeric settings (W/H/FPS) found in config, using defaults for all.")
                         return defaults 
        except (json.JSONDecodeError, IOError, Exception) as e:
            print(f"Error loading host config: {e}, using defaults.")
            return defaults
            
        return settings
        
    def save_settings(self):
        """Save current settings to config file."""
        try:
            width = int(self.capture_width.get())
            height = int(self.capture_height.get())
            fps = int(self.capture_fps.get())
            fidelity = self.fidelity_var.get().upper()
            port = int(self.port_var.get()) # Get port
            
            # Validate before saving
            if width <=0 or height <=0 or fps <=0: raise ValueError("Invalid dimensions or FPS")
            if fidelity not in ['JPEG', 'PNG']: raise ValueError("Invalid fidelity setting") 
            if port <= 1023 or port > 65535: raise ValueError(f"Invalid port number: {port}") # Validate port
            
            config = {
                'capture_width': width, 
                'capture_height': height,
                'capture_fps': fps,
                'fidelity': fidelity,
                'port': port # Save port
            }
            with open(HOST_CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"Saved settings: {width}x{h} @ {fps} FPS, Fidelity: {fidelity}, Port: {port}")
        except (tk.TclError, ValueError, IOError, Exception) as e:
            print(f"Error saving host config: {e}")

    async def async_cleanup(self):
        """Async cleanup function for Zeroconf"""
        # Check if zeroconf and service_info exist and if service is registered
        if hasattr(self, 'zeroconf') and self.zeroconf and \
           hasattr(self, 'service_info') and self.service_info and \
           self.service_info.name in self.zeroconf.services:
            try:
                print(f"Unregistering service: {self.service_info.name}")
                await self.zeroconf.async_unregister_service(self.service_info)
            except Exception as e:
                 print(f"Error during async_unregister_service: {e}")
        # Close zeroconf itself
        if hasattr(self, 'zeroconf') and self.zeroconf:
            try:
                print("Closing Zeroconf connection.")
                await self.zeroconf.async_close()
            except Exception as e:
                 print(f"Error during async_close: {e}")

    def cleanup(self):
        """Cleanup function called when the application exits"""
        print("Starting cleanup...")
        self.running = False
        self.save_settings() # Save settings before closing
        
        # --- Close Sockets First --- 
        try:
             if self.server_socket:
                  print("Closing server socket...")
                  self.server_socket.close()
                  self.server_socket = None
        except Exception as e:
             print(f"Error closing server socket: {e}")
             pass
        try:
             if self.control_server_socket:
                  print("Closing control server socket...")
                  self.control_server_socket.close()
                  self.control_server_socket = None
        except Exception as e:
             print(f"Error closing control server socket: {e}")
             pass
        # --- End Close Sockets ---
        
        # --- Zeroconf Cleanup --- 
        try:
            # Run async cleanup in a way that works if called from non-async context
            print("Running async Zeroconf cleanup...")
            try:
                 loop = asyncio.get_running_loop()
                 # If already in an event loop, schedule it
                 loop.create_task(self.async_cleanup())
                 # Need a way to wait? This might not work reliably from atexit.
                 # A better approach might be to run_until_complete in stop(), 
                 # but atexit is tricky.
                 # Let's try running it synchronously if no loop is running.
            except RuntimeError: # No running event loop
                 asyncio.run(self.async_cleanup()) 
            
            # Old synchronous attempt (can cause issues with async zeroconf)
            # loop = asyncio.new_event_loop()
            # asyncio.set_event_loop(loop)
            # loop.run_until_complete(self.async_cleanup())
            # loop.close()
            print("Async Zeroconf cleanup finished.")
        except Exception as e:
            print(f"Error during Zeroconf cleanup initiation: {e}")
            pass
        # --- End Zeroconf Cleanup --- 
        print("Cleanup finished.")
        
    def stop(self):
        print("Stopping server...")
        self.running = False # Signal threads to stop
        
        # --- Zeroconf Unregister --- 
        # We need to run the async part here cleanly before sockets might close
        if self.zeroconf and self.service_info:
            print("Attempting synchronous Zeroconf unregister/close...")
            try:
                 # Prefer asyncio.run for cleaner handling if possible
                 asyncio.run(self.async_cleanup())
                 self.service_info = None # Clear service info after unregistering
                 self.zeroconf = None # Clear zeroconf after closing
                 print("Zeroconf unregister/close completed.")
            except Exception as e:
                 print(f"Error running async Zeroconf cleanup in stop(): {e}")
                 # Fallback or just log? Maybe try old loop method? No, likely unsafe.
        # --- End Zeroconf --- 

        # --- Close listening sockets AFTER unregistering --- 
        try:
             if self.server_socket:
                  print("Closing server socket in stop()...")
                  self.server_socket.close()
                  self.server_socket = None
        except Exception as e:
             print(f"Error closing server socket in stop(): {e}")
             pass
        try:
             if self.control_server_socket:
                  print("Closing control server socket in stop()...")
                  self.control_server_socket.close()
                  self.control_server_socket = None
        except Exception as e:
             print(f"Error closing control server socket in stop(): {e}")
             pass
        # --- End Close Sockets --- 

        # Update UI (safe checks might be needed if UI can be destroyed)
        try:
            if self.root and self.root.winfo_exists():
                self.status_label.config(text="Server: Stopped")
                self.start_button.config(state="normal")
                self.stop_button.config(state="disabled")
                self.clients_label.config(text="Connected Clients: 0")
                # Enable Settings Entries
                self.width_entry.config(state="normal")
                self.height_entry.config(state="normal")
                self.fps_entry.config(state="normal")
                self.fidelity_combo.config(state="readonly")
                self.port_entry.config(state="normal")
            else:
                 print("Stop: UI Root window not found, skipping UI updates.")
        except tk.TclError as e:
             print(f"Stop: TclError updating UI: {e}")
        except Exception as e:
             print(f"Stop: Unexpected error updating UI: {e}")
        
        self.clients.clear()
        print("Server stopped.")
        
    def on_closing(self):
        """Handle window closing"""
        self.cleanup()
        self.root.destroy()
        
    def setup_ui(self):
        self.root.title("Screen Share Host")
        self.root.geometry("400x300")
        
        # Status frame
        status_frame = ttk.LabelFrame(self.root, text="Status", padding="10")
        status_frame.pack(fill="x", padx=10, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Server: Stopped")
        self.status_label.pack(fill="x")
        
        # IP Address frame with copy button
        ip_frame = ttk.Frame(status_frame)
        ip_frame.pack(fill="x", pady=5)
        
        self.ip_label = ttk.Label(ip_frame, text=f"IP Address: {self.host_ip}")
        self.ip_label.pack(side="left")
        
        def copy_ip():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.host_ip)
            self.status_label.config(text="IP Address copied to clipboard!")
            self.root.after(2000, lambda: self.status_label.config(text="Server: Running"))
            
        copy_button = ttk.Button(ip_frame, text="Copy IP", command=copy_ip)
        copy_button.pack(side="right", padx=5)
        
        self.port_label = ttk.Label(status_frame, text=f"Configured Port: {self.port}") # Show configured port
        self.port_label.pack(fill="x")
        
        self.clients_label = ttk.Label(status_frame, text="Connected Clients: 0")
        self.clients_label.pack(fill="x")
        
        # Controls frame
        controls_frame = ttk.LabelFrame(self.root, text="Controls", padding="10")
        controls_frame.pack(fill="x", padx=10, pady=5)
        
        self.start_button = ttk.Button(controls_frame, text="Start Server", command=self.start)
        self.start_button.pack(side="left", padx=5)
        
        self.stop_button = ttk.Button(controls_frame, text="Stop Server", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=5)
        
        # Settings frame
        settings_frame = ttk.LabelFrame(self.root, text="Settings", padding="10")
        settings_frame.pack(fill="x", padx=10, pady=5)
        
        settings_grid_frame = ttk.Frame(settings_frame)
        settings_grid_frame.pack(anchor="w")

        # Row 0: Dimensions
        ttk.Label(settings_grid_frame, text="Width:").grid(row=0, column=0, padx=(0, 5), pady=2, sticky="w")
        self.width_entry = ttk.Entry(settings_grid_frame, textvariable=self.capture_width, width=5)
        self.width_entry.grid(row=0, column=1, padx=(0, 10), pady=2, sticky="w")

        ttk.Label(settings_grid_frame, text="Height:").grid(row=0, column=2, padx=(0, 5), pady=2, sticky="w")
        self.height_entry = ttk.Entry(settings_grid_frame, textvariable=self.capture_height, width=5)
        self.height_entry.grid(row=0, column=3, padx=(0, 10), pady=2, sticky="w")
        
        ttk.Label(settings_grid_frame, text="px").grid(row=0, column=4, padx=(0, 5), pady=2, sticky="w") # Simplified label

        # Row 1: FPS & Fidelity
        ttk.Label(settings_grid_frame, text="Target FPS:").grid(row=1, column=0, padx=(0, 5), pady=2, sticky="w")
        self.fps_entry = ttk.Entry(settings_grid_frame, textvariable=self.capture_fps, width=5)
        self.fps_entry.grid(row=1, column=1, padx=(0, 10), pady=2, sticky="w")

        ttk.Label(settings_grid_frame, text="Fidelity:").grid(row=1, column=2, padx=(0, 5), pady=2, sticky="w")
        self.fidelity_combo = ttk.Combobox(settings_grid_frame, textvariable=self.fidelity_var, values=["JPEG", "PNG"], width=7, state="readonly") # Added Fidelity Combobox
        self.fidelity_combo.grid(row=1, column=3, columnspan=2, padx=(0, 10), pady=2, sticky="w") # Span 2 cols
        
        # Row 2: Port
        ttk.Label(settings_grid_frame, text="Port:").grid(row=2, column=0, padx=(0, 5), pady=(5, 2), sticky="w") # Add padding top
        self.port_entry = ttk.Entry(settings_grid_frame, textvariable=self.port_var, width=7)
        self.port_entry.grid(row=2, column=1, padx=(0, 10), pady=(5, 2), sticky="w")
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def update_ui(self):
        # This function now runs in the main thread via root.after
        # It processes messages from the queue to update UI elements
        try:
            while not self.status_queue.empty():
                status = self.status_queue.get_nowait()
                # print(f"UI Update Processing: {status}") # Debug log
                if status.startswith("client_connected"):
                    addr_str = status.split(":", 1)[1]
                    if addr_str not in self.clients:
                         self.clients.append(addr_str)
                         # print(f"Client added: {addr_str}, List: {self.clients}") # Debug log
                    self.clients_label.config(text=f"Connected Clients: {len(self.clients)}")
                elif status.startswith("client_disconnected"):
                    addr_str = status.split(":", 1)[1]
                    # --- Safely remove client --- 
                    try:
                        self.clients.remove(addr_str)
                        # print(f"Client removed: {addr_str}, List: {self.clients}") # Debug log
                    except ValueError:
                         # print(f"Client already removed or not found: {addr_str}") # Debug log
                         pass # Ignore if client already removed (e.g., by stop() or multiple disconnect messages)
                    # --- End Safe Remove ---
                    self.clients_label.config(text=f"Connected Clients: {len(self.clients)}")
                elif status.startswith("status_update"):
                     msg = status.split(":", 1)[1]
                     self.status_label.config(text=msg)
                     # print(f"Status updated: {msg}") # Debug log
                     
        except queue.Empty:
            pass # No messages to process
        except Exception as e:
             print(f"[ERROR] Unexpected error in update_ui: {e}")
             # import traceback
             # traceback.print_exc()
             
        # Reschedule self if the server is supposed to be running
        if self.running:
             self.root.after(100, self.update_ui) # Check queue every 100ms
        # else:
             # print("UI Update: Not rescheduling as server stopped.") # Debug log
        
    def start(self):
        # --- Validate and Get Settings --- 
        try:
            w = self.capture_width.get()
            h = self.capture_height.get()
            fps = self.capture_fps.get()
            fidelity = self.fidelity_var.get().upper()
            port = self.port_var.get()
            if port <= 1023 or port > 65535: raise ValueError(f"Invalid Port: {port}.")
            if w <= 0 or h <= 0 or fps <= 0: raise ValueError("Dimensions/FPS must be positive")
            if fidelity not in ["JPEG", "PNG"]: raise ValueError("Invalid Fidelity setting")
            
            # Update internal port state
            self.port = port
            self.control_port = self.port + CONTROL_PORT_OFFSET
            self.port_label.config(text=f"Configured Port: {self.port}") # Update UI label
            print(f"Attempting to start server on port {self.port}...")
            
        except (tk.TclError, ValueError) as e:
            self.status_label.config(text=f"Error: Invalid settings - {e}")
            print(f"[ERROR] Invalid settings entered: {e}")
            return
        # --- End Validate --- 
        
        # --- Create and Bind Sockets --- 
        try:
            print("Binding sockets...")
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            self.control_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_server_socket.bind((self.host, self.control_port))
            self.control_server_socket.listen(5)
            print(f"Sockets bound successfully to port {self.port} and {self.control_port}.")
        except OSError as bind_e:
            self.status_label.config(text=f"Error: Failed to bind to port {self.port} - {bind_e}")
            print(f"[ERROR] Failed to bind sockets: {bind_e}")
            # Clean up partially created sockets
            if self.server_socket: self.server_socket.close(); self.server_socket = None
            if self.control_server_socket: self.control_server_socket.close(); self.control_server_socket = None
            return
        except Exception as e:
             print(f"[ERROR] Unexpected error binding sockets: {e}")
             if self.server_socket: self.server_socket.close(); self.server_socket = None
             if self.control_server_socket: self.control_server_socket.close(); self.control_server_socket = None
             return
        # --- End Socket Binding --- 
        
        self.running = True
        # --- Create Zeroconf and Register Service --- 
        try:
            print("Registering Zeroconf service...")
            self.zeroconf = Zeroconf() # Create new instance
            instance_name = socket.gethostname()
            unique_service_name = f"{instance_name}._screenshare._tcp.local."
            
            # Use a list of addresses for better network compatibility
            addresses = []
            for ip in self.all_ips:
                try:
                    addresses.append(socket.inet_aton(ip))
                except:
                    print(f"Error converting IP {ip} to network format")
            
            # Fall back to main IP if no addresses found
            if not addresses:
                addresses = [socket.inet_aton(self.host_ip)]
                
            self.service_info = ServiceInfo(
                type_="_screenshare._tcp.local.",
                name=unique_service_name,
                addresses=addresses,  # Use all available IPs
                port=self.port,
                properties={'instance_name': instance_name} 
            )
            print(f"Advertising service as: {unique_service_name} on port {self.port} with IPs: {self.all_ips}")
            self.zeroconf.register_service(self.service_info)
            print("Zeroconf service registered successfully.")
        except (Zeroconf.NonUniqueNameException, OSError) as reg_e: # Catch OSError too (e.g., network issues)
             self.status_label.config(text=f"Error: Service registration failed - {reg_e}")
             print(f"[ERROR] Zeroconf registration failed: {reg_e}")
             self.running = False
             # Clean up sockets that were successfully bound
             if self.server_socket: self.server_socket.close(); self.server_socket = None
             if self.control_server_socket: self.control_server_socket.close(); self.control_server_socket = None
             if self.zeroconf: self.zeroconf.close(); self.zeroconf = None # Close zeroconf instance
             return
        except Exception as e:
             print(f"[ERROR] Unexpected error registering service: {e}")
             self.running = False
             if self.server_socket: self.server_socket.close(); self.server_socket = None
             if self.control_server_socket: self.control_server_socket.close(); self.control_server_socket = None
             if self.zeroconf: self.zeroconf.close(); self.zeroconf = None
             return
        # --- End Zeroconf --- 
        
        # --- Update UI and Start Threads --- 
        self.status_label.config(text=f"Server: Running on port {self.port} ({w}x{h} @ {fps} FPS, {fidelity})")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        # Disable Settings Entries
        self.width_entry.config(state="disabled")
        self.height_entry.config(state="disabled")
        self.fps_entry.config(state="disabled")
        self.fidelity_combo.config(state="disabled") 
        self.port_entry.config(state="disabled") 
        
        # Start background threads
        # Ensure update_ui is run via root.after if it interacts heavily with Tkinter state
        # Let's run it via root.after for safety
        self.root.after(100, self.update_ui) 
        # threading.Thread(target=self.update_ui, daemon=True).start()
        
        threading.Thread(target=self.accept_connections, daemon=True).start()
        threading.Thread(target=self.accept_control_connections, daemon=True).start()
        print("Server threads started.")

    def accept_connections(self):
        print("[*] Stream connection acceptor running...")
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"[*] Accepted stream connection from {addr}")
                thread = threading.Thread(target=self.handle_client, args=(client_socket, addr), daemon=True)
                self.client_threads.append(thread)
                thread.start()
            except OSError as e:
                 if self.running: # Only print error if we weren't expecting the shutdown
                      print(f"[ERROR] Error accepting stream connection: {e}")
                 break # Exit loop if socket is closed
            except Exception as e:
                 if self.running:
                      print(f"[ERROR] Unexpected error in accept_connections: {e}")
                 break
        print("[*] Stream connection acceptor stopped.")
        
    def accept_control_connections(self):
        """Accepts incoming connections on the control port."""
        print("[*] Control connection acceptor running...")
        while self.running:
            try:
                control_client_socket, addr = self.control_server_socket.accept()
                print(f"[*] Accepted control connection from {addr}")
                # --- SET TCP_NODELAY --- 
                try:
                    control_client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    print(f"[*] Set TCP_NODELAY for control client {addr}")
                except Exception as nodelay_e:
                    print(f"[Warning] Could not set TCP_NODELAY for {addr}: {nodelay_e}")
                # --- END SET ---
                thread = threading.Thread(target=self.handle_control_client, args=(control_client_socket, addr), daemon=True)
                self.control_threads.append(thread)
                thread.start()
            except OSError as e:
                 if self.running: # Only print error if we weren't expecting the shutdown
                      print(f"[ERROR] Error accepting control connection: {e}")
                 break # Exit loop if socket is closed
            except Exception as e:
                 if self.running:
                      print(f"[ERROR] Unexpected error in accept_control_connections: {e}")
                 break
        print("[*] Control connection acceptor stopped.")

    def handle_control_client(self, client_socket, addr):
        """Handles incoming control messages (keyboard/mouse) from a client."""
        print(f"[*] Handling control client {addr}")
        buffer = ""
        try:
            while self.running:
                try:
                    # Receive data in chunks
                    data = client_socket.recv(1024)
                    if not data:
                        print(f"[*] Control client {addr} disconnected (no data).")
                        break
                        
                    buffer += data.decode('utf-8')
                    
                    # Process complete messages (newline terminated)
                    while '\n' in buffer:
                        message, buffer = buffer.split('\n', 1)
                        try:
                            key_data = json.loads(message)
                            event_type = key_data.get('type')
                            keycode = key_data.get('keycode')
                            char = key_data.get('char')
                            
                            sim_key = get_sim_key(keycode, char)
                            
                            if sim_key is not None:
                                if event_type == 'key_press':
                                    print(f"[Control {addr}] Simulating PRESS: {sim_key} (keycode={keycode}, char='{char}')")
                                    self.keyboard_controller.press(sim_key)
                                elif event_type == 'key_release':
                                    print(f"[Control {addr}] Simulating RELEASE: {sim_key} (keycode={keycode}, char='{char}')")
                                    self.keyboard_controller.release(sim_key)
                                else:
                                    print(f"[Control Warning] Unknown event type: {event_type}")
                            else:
                                # Already warned in get_sim_key
                                pass
                                
                        except json.JSONDecodeError:
                            print(f"[Control ERROR {addr}] Invalid JSON received: {message}")
                        except Exception as e:
                            print(f"[Control ERROR {addr}] Error processing message: {e}")
                            # Optionally print traceback
                            # import traceback
                            # traceback.print_exc()
                            
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    print(f"[*] Control client {addr} connection error.")
                    break
                except UnicodeDecodeError:
                     print(f"[Control ERROR {addr}] Received non-UTF8 data.")
                     # Clear buffer maybe?
                     buffer = ""
                     continue # Try to recover?
                except Exception as e:
                     print(f"[Control ERROR {addr}] Unexpected error in receive loop: {e}")
                     break
                     
        except Exception as e:
             print(f"[Control ERROR {addr}] Fatal error in handle_control_client: {e}")
        finally:
            print(f"[*] Cleaning up control client handler {addr}")
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                 pass # Ignore if already closed
            finally:
                 client_socket.close()
            # Remove thread from list? Requires thread-safe list or different approach
            # Currently relying on daemon=True for cleanup

    def handle_client(self, client_socket, addr):
        # Get current settings at the start of handling this client
        current_width = self.capture_width.get()
        current_height = self.capture_height.get()
        current_fps = self.capture_fps.get()
        current_fidelity = self.fidelity_var.get().upper() # Get Fidelity
        
        monitor = {"top": 0, "left": 0, "width": current_width, "height": current_height}
        delay = 1.0 / current_fps if current_fps > 0 else 1/60.0 
        
        # Determine encoding based on fidelity setting
        if current_fidelity == "PNG":
            encode_format = '.png'
            encode_params = [] # No quality setting for PNG
            print(f"[*] Using PNG encoding for {addr}")
        else: # Default to JPEG
            encode_format = '.jpg'
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95] # Keep high quality JPEG
            print(f"[*] Using JPEG encoding for {addr}")
        
        try:
            print(f"Starting client handler for {addr} with size {current_width}x{current_height} @ {current_fps} FPS, Fidelity: {current_fidelity} (delay: {delay:.4f}s)")
            
            # --- Send Dimensions and Format First --- 
            try:
                initial_info = {
                    'width': current_width, 
                    'height': current_height, 
                    'format': current_fidelity.lower() # Send format (lowercase 'jpeg' or 'png')
                }
                info_json = json.dumps(initial_info).encode('utf-8')
                info_size = struct.pack('>I', len(info_json))
                
                print(f"[*] Sending initial info {initial_info} ({len(info_json)} bytes) to {addr}")
                client_socket.sendall(info_size)
                client_socket.sendall(info_json)
                print(f"[*] Initial info sent successfully to {addr}")
            except (socket.error, ConnectionResetError, BrokenPipeError) as e:
                print(f"[ERROR] Failed to send initial info to {addr}: {e}. Closing connection.")
                client_socket.close()
                self.status_queue.put(f"client_disconnected:{addr}") 
                return
            except Exception as e:
                 print(f"[ERROR] Unexpected error sending initial info to {addr}: {e}. Closing connection.")
                 client_socket.close()
                 self.status_queue.put(f"client_disconnected:{addr}")
                 return
            # --- End Send Initial Info ---
            
            # --- Set TCP_NODELAY for the stream socket --- 
            try:
                 client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                 print(f"[*] Set TCP_NODELAY for stream client {addr}")
            except Exception as nodelay_e:
                 print(f"[Warning] Could not set TCP_NODELAY for stream {addr}: {nodelay_e}")
            # --- End Set TCP_NODELAY ---
            
            thread_sct = mss.mss()
            frame_count = 0 # Frame counter for logging
            log_interval = 120 # Log every 120 frames (e.g., every 2 seconds at 60fps)
            
            while self.running:
                try:
                    frame_start_time = time.perf_counter()
                    
                    screenshot = thread_sct.grab(monitor)
                    frame = np.array(screenshot)
                    
                    ok, buffer = cv2.imencode(encode_format, frame, encode_params)
                    if not ok:
                        # print(f"[ERROR {addr}] Frame encoding failed (Format: {encode_format}). Skipping frame.")
                        continue 
                    
                    size = len(buffer)
                    size_data = size.to_bytes(4, byteorder='big')
                    
                    # Send frame size and data
                    client_socket.sendall(size_data)
                    client_socket.sendall(buffer.tobytes())
                    
                    # Control frame rate
                    frame_end_time = time.perf_counter()
                    elapsed_time = frame_end_time - frame_start_time
                    sleep_time = delay - elapsed_time
                    
                    # --- Add Frame Timing Log --- 
                    frame_count += 1
                    if frame_count % log_interval == 0:
                         print(f"[Host {addr} Frame {frame_count}] Process Time: {elapsed_time*1000:.2f} ms, Target Delay: {delay*1000:.2f} ms, Sleep Time: {max(0, sleep_time)*1000:.2f} ms")
                    # --- End Log ---
                         
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                        
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError) as e:
                    print(f"Client {addr} disconnected: {str(e)}")
                    break
                    
        except Exception as e:
            if self.running:  # Only print error if we're still running
                print(f"Error handling client {addr}: {str(e)}")
        finally:
            print(f"Cleaning up client handler for {addr}")
            # Clean up thread-specific MSS instance
            try:
                thread_sct.close()
            except:
                pass
            try:
                client_socket.close()
            except:
                pass
            self.status_queue.put(f"client_disconnected:{addr}")
            
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    host = ScreenShareHost()
    try:
        host.run()
    except KeyboardInterrupt:
        print("\nShutting down host...")
        host.cleanup() 