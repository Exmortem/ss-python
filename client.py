import socket
import cv2
import numpy as np
from zeroconf import ServiceBrowser, Zeroconf
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import json
import os
import queue
import sys
import struct # Added for unpacking size

# Control Port offset
CONTROL_PORT_OFFSET = 1

class ScreenShareClient:
    def __init__(self):
        # --- Create Root Window FIRST --- 
        self.root = tk.Tk() 
        # --- End Create Root --- 
        
        self.zeroconf = Zeroconf()
        self.host_info = None
        self.running = False
        self.config_file = "client_config.json"
        self.frame_queue = queue.Queue(maxsize=10)
        self._update_frame_count = 0
        self.stream_socket = None # Renamed for clarity
        self.control_socket = None # New socket for control messages
        self.stream_window = None
        self.canvas = None
        self.stream_label = None
        self.stream_thread = None
        self.control_thread = None # Thread for sending control signals
        self.image_queue = queue.Queue(maxsize=60)  # Increased queue size for better buffering
        self.stop_event = threading.Event()
        self.last_ip = self.load_last_ip()
        self.connected = False
        self.stream_width = 0
        self.stream_height = 0
        self.stream_format = "jpeg" # Default, will be updated from host
        self.update_id = None # Keep this to store the ID of the next scheduled update
        self.tk_image = None # Keep reference to PhotoImage
        self.canvas_image_item = None # ID of the image item on canvas
        
        # --- Frame rate settings ---
        self.unlimited_frame_rate = tk.BooleanVar(value=True)
        # --- End frame rate settings ---
        
        # --- Statistics tracking ---
        self.stats = {
            'frames_received': 0,           # Total frames received 
            'frames_displayed': 0,          # Total frames displayed
            'frames_dropped': 0,            # Total frames dropped
            'last_stats_reset': time.time(),
            'fps_received': 0.0,            # Current receiving FPS
            'fps_displayed': 0.0,           # Current displaying FPS
            'processing_times': [],         # List to calculate average processing time
            'max_processing_time': 0.0,
            'queue_max_size': 30,           # Should match the queue size
            # New interval tracking
            'interval_frames_received': 0,  # Frames received in current interval
            'interval_frames_displayed': 0, # Frames displayed in current interval
            'last_interval_time': time.time() # Last interval start time
        }
        self.stats_update_interval = 1.0  # Update stats display every second
        self.stats_last_update = time.time()
        # --- End Statistics tracking ---
        
        # --- Zeroconf discovery storage (Needs root implicitly, safe now) --- 
        self.discovered_services = {}
        self.discovered_list_var = tk.StringVar() # Now safe to create
        # --- End Zeroconf --- 
        
        # Setup UI (Configures the existing self.root)
        self.setup_ui()
        
        # Start browsing after UI is setup
        self.browser = ServiceBrowser(self.zeroconf, "_screenshare._tcp.local.", listener=self)
        
    def load_last_ip(self):
        """Load the last successful IP address from config file (ignore frame rate settings)"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Only return the last IP
                    return config.get('last_ip', '192.168.10.2')
        except:
            pass
        return '192.168.10.2'  # Default IP
        
    def save_last_ip(self, ip):
        """Save the last successful IP address to config file (ignore frame rate settings)"""
        print(f"Attempting to save settings to {self.config_file}") # Add log
        config = {
            'last_ip': ip
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f)
        print(f"Successfully saved IP: {ip}") # Add success log
        
    # --- Zeroconf Listener Methods --- 
    # These methods are called by the ServiceBrowser
    def remove_service(self, zeroconf, type, name):
        """Called by Zeroconf when a service is removed."""
        print(f"Service {name} removed")
        # Extract friendly name (hostname part)
        try:
            friendly_name = name.split('.')[0]
        except IndexError:
             friendly_name = name # Fallback if name format is unexpected
             
        if friendly_name in self.discovered_services:
            del self.discovered_services[friendly_name]
            self.root.after(0, self.update_service_list) # Schedule UI update in main thread

    def add_service(self, zeroconf, type, name):
        """Called by Zeroconf when a service is added or updated."""
        # Use get_service_info with a timeout
        info = zeroconf.get_service_info(type, name, timeout=1000) # 1 second timeout
        if info:
            print(f"Service {name} added/updated, info: {info}")
            # Extract friendly name (hostname part)
            try:
                friendly_name = name.split('.')[0]
            except IndexError:
                 friendly_name = name # Fallback
                 
            self.discovered_services[friendly_name] = info
            self.root.after(0, self.update_service_list) # Schedule UI update in main thread
        else:
            print(f"Could not get info for service {name}")

    def update_service(self, zeroconf, type, name):
        """Called by Zeroconf when a service's details (like properties) change."""
        # For simplicity, we just re-request the info as if it were added
        print(f"Service {name} updated, re-querying info...")
        self.add_service(zeroconf, type, name)
    # --- End Zeroconf Listener Methods --- 

    def setup_ui(self):
        # --- Configure Root Window (already created in __init__) --- 
        self.root.title("Screen Share Client Controls")
        # self.root.geometry(...) # Set geometry if needed
        # --- End Configure --- 
        
        # --- Discovery Frame (Using Listbox) --- 
        discovery_frame = ttk.LabelFrame(self.root, text="Discovered Hosts", padding="10")
        discovery_frame.pack(fill="x", padx=10, pady=5)
        
        self.service_listbox = tk.Listbox(
             discovery_frame, 
             listvariable=self.discovered_list_var, 
             height=4, 
             exportselection=False # Keep selection visible
        )
        self.service_listbox.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.service_listbox.bind("<<ListboxSelect>>", self.on_service_select)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(discovery_frame, orient="vertical", command=self.service_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.service_listbox.config(yscrollcommand=scrollbar.set)
        
        # Connect button now connects to the SELECTED host from the listbox (moved here)
        self.connect_button = ttk.Button(discovery_frame, text="Connect to Selected", command=self.connect_to_selected_host, state="disabled") 
        self.connect_button.pack(fill="x", padx=5, pady=(5, 0))
        # --- End Discovery Frame --- 
        
        # Status frame
        status_frame = ttk.LabelFrame(self.root, text="Status", padding="10") # Restored padding
        status_frame.pack(fill="x", padx=10, pady=5) # Restored padding/margins
        
        self.status_label = ttk.Label(status_frame, text="Status: Searching for host...")
        self.status_label.pack(fill="x")
        
        # --- Stats Frame --- 
        stats_frame = ttk.LabelFrame(self.root, text="Performance Stats", padding="10")
        stats_frame.pack(fill="x", padx=10, pady=5)
        
        stats_grid = ttk.Frame(stats_frame)
        stats_grid.pack(fill="x", padx=5, pady=5)
        
        # Row 0: FPS
        ttk.Label(stats_grid, text="Receiving:").grid(row=0, column=0, sticky="w", padx=5)
        self.fps_received_label = ttk.Label(stats_grid, text="0 FPS")
        self.fps_received_label.grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(stats_grid, text="Displaying:").grid(row=0, column=2, sticky="w", padx=5)
        self.fps_displayed_label = ttk.Label(stats_grid, text="0 FPS")
        self.fps_displayed_label.grid(row=0, column=3, sticky="w", padx=5)
        
        # Row 1: Frames
        ttk.Label(stats_grid, text="Dropped:").grid(row=1, column=0, sticky="w", padx=5)
        self.frames_dropped_label = ttk.Label(stats_grid, text="0")
        self.frames_dropped_label.grid(row=1, column=1, sticky="w", padx=5)
        
        ttk.Label(stats_grid, text="Queue:").grid(row=1, column=2, sticky="w", padx=5)
        self.queue_usage_label = ttk.Label(stats_grid, text="0%")
        self.queue_usage_label.grid(row=1, column=3, sticky="w", padx=5)
        
        # Row 2: Processing time
        ttk.Label(stats_grid, text="Proc Time:").grid(row=2, column=0, sticky="w", padx=5)
        self.avg_processing_label = ttk.Label(stats_grid, text="0 ms")
        self.avg_processing_label.grid(row=2, column=1, sticky="w", padx=5)
        
        ttk.Label(stats_grid, text="Max Time:").grid(row=2, column=2, sticky="w", padx=5)
        self.max_processing_label = ttk.Label(stats_grid, text="0 ms")
        self.max_processing_label.grid(row=2, column=3, sticky="w", padx=5)
        
        # Add a reset button
        self.reset_stats_button = ttk.Button(stats_frame, text="Reset Stats", command=self.reset_statistics)
        self.reset_stats_button.pack(anchor="e", padx=5, pady=5)
        # --- End Stats Frame ---
        
        # Manual connection frame
        manual_frame = ttk.LabelFrame(self.root, text="Manual Connect", padding="10") # Restored padding
        manual_frame.pack(fill="x", padx=10, pady=5) # Restored padding/margins
        
        # Restore pack layout for manual connection
        ttk.Label(manual_frame, text="Host IP:").pack(side="left", padx=5)
        self.ip_entry = ttk.Entry(manual_frame, width=15)
        self.ip_entry.pack(side="left", padx=5)
        self.ip_entry.insert(0, self.last_ip)  # Use last successful IP
        
        ttk.Label(manual_frame, text="Port:").pack(side="left", padx=5)
        self.port_entry = ttk.Entry(manual_frame, width=6)
        self.port_entry.pack(side="left", padx=5)
        self.port_entry.insert(0, "8485")
        
        self.manual_connect_button = ttk.Button(manual_frame, text="Connect", command=self.manual_connect)
        self.manual_connect_button.pack(side="left", padx=5)

        # Controls frame 
        controls_frame = ttk.LabelFrame(self.root, text="Controls", padding="10")
        controls_frame.pack(fill="x", padx=10, pady=5)
        
        # Remove duplicate connect button from here, only keep disconnect
        self.disconnect_button = ttk.Button(controls_frame, text="Disconnect", command=self.stop, state="disabled")
        self.disconnect_button.pack(side="left", padx=5)
        
        # Initialize stream window variable, don't create it yet
        self.stream_window = None
        self.canvas = None # Initialize canvas as well
        
        # Bind escape key to exit
        self.root.bind('<Escape>', lambda e: self.on_closing())
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # --- Call update_service_list AFTER all widgets are created --- 
        self.update_service_list()
        # --- End Call --- 
        
    def create_stream_window(self):
        """Create the borderless stream window using received dimensions."""
        # If window already exists and is valid, just show it
        if self.stream_window and self.stream_window.winfo_exists():
            self.stream_window.deiconify() 
            return
            
        # If window doesn't exist or was destroyed, create it anew
        self.stream_window = tk.Toplevel()
        self.stream_window.title("Screen Share Stream")
        self.stream_window.attributes('-topmost', True)  # Keep window on top
        self.stream_window.overrideredirect(True)  # Remove window decorations
        
        # Ensure minimum dimensions for very small streams
        display_width = max(150, self.stream_width)
        display_height = max(30, self.stream_height)
        
        # --- Use stream dimensions --- 
        geometry_string = f"{display_width}x{display_height}+0+0"
        print(f"[Debug] Setting stream window geometry: {geometry_string}")
        self.stream_window.geometry(geometry_string)  # Position at (0,0)
        # --- End Use ---
        
        # Create canvas for stream, removing its border
        self.canvas = tk.Canvas(
            self.stream_window, 
            width=self.stream_width,   # Use actual stream width
            height=self.stream_height, # Use actual stream height
            borderwidth=0,         
            highlightthickness=0,  
            bg='black'             
        )
        self.canvas.pack(fill="both", expand=True)
        
        # Force a focus and update to ensure window is initialized properly
        self.stream_window.focus_force()
        self.stream_window.update()
        
        # Add close button (linked to stop, which calls on_closing)
        # Adjust position based on width
        close_button_x = max(0, display_width - 30) # Ensure positive X
        close_button = ttk.Button(self.stream_window, text="X", width=3, command=self.stop)
        close_button.place(x=close_button_x, y=5)
        
        # Bind keys and set focus
        self.stream_window.bind("<KeyPress>", self.on_key_press)
        self.stream_window.bind("<KeyRelease>", self.on_key_release)
        self.stream_window.focus_set()

        self.stream_window.deiconify()
        
        # Print diagnostic info
        print(f"[Debug] Stream window created with dimensions: {self.stream_width}x{self.stream_height}")
        print(f"[Debug] Canvas created with dimensions: {self.canvas.winfo_width()}x{self.canvas.winfo_height()}")
        self.root.after(500, self._check_canvas_size)  # Check size after things settle
    
    def _check_canvas_size(self):
        """Debug method to check canvas sizing after window creation"""
        if self.canvas and self.canvas.winfo_exists():
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            print(f"[Debug] Canvas size after 500ms: {canvas_width}x{canvas_height}")
            
            # If there's a mismatch, try forcing the correct size
            if canvas_width != self.stream_width or canvas_height != self.stream_height:
                print(f"[Debug] Fixing canvas size to match stream: {self.stream_width}x{self.stream_height}")
                self.canvas.config(width=self.stream_width, height=self.stream_height)
                self.stream_window.geometry(f"{self.stream_width}x{self.stream_height}+0+0")

    def on_key_press(self, event):
        """Callback for key press events on the stream window."""
        self.send_key_event('key_press', event)

    def on_key_release(self, event):
        """Callback for key release events on the stream window."""
        self.send_key_event('key_release', event)
        
    def send_key_event(self, event_type, event):
        """Formats and sends key event data over the control socket."""
        # --- REMOVED TEMPORARY LOGGING ---
        # print(f"[Client KEY EVENT] Type={event_type}, Keysym={event.keysym}, Char='{event.char}', Keycode={event.keycode}")
        # --- END LOGGING ---
        if self.control_socket and self.running:
            try:
                # Focus check (optional, binding should handle it, but belt-and-suspenders)
                # focused_widget = self.root.focus_get()
                # if focused_widget != self.stream_window and focused_widget != self.canvas:
                #     # print("Ignoring key event, stream window not focused")
                #     return
                    
                # Use keysym for simplicity, might need keycode/char for complex mapping later
                key_data = {
                    'type': event_type,
                    'keysym': event.keysym,
                    'char': event.char, # Might be empty for special keys
                    'keycode': event.keycode # Platform-specific key code
                }
                message = json.dumps(key_data).encode('utf-8')
                # Simple newline termination for control messages
                self.control_socket.sendall(message + b'\n') 
                # print(f"Sent: {key_data}") # Verbose log
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                print(f"Control socket error sending key event: {e}")
                # Consider attempting to reconnect or stopping cleanly
                self.root.after(0, lambda: self.status_label.config(text=f"Control connection error: {e}"))
                # self.stop() # Optionally stop if control fails
            except Exception as e:
                 print(f"Unexpected error sending key event: {e}")

    def connect_to_selected_host(self):
        """Connect to the host selected in the discovery listbox."""
        selection_indices = self.service_listbox.curselection()
        if not selection_indices:
            self.status_label.config(text="Error: No host selected from the list.")
            print("Connect failed: No host selected.")
            return
            
        selected_index = selection_indices[0]
        # Get the friendly name from the listbox content
        friendly_name = self.service_listbox.get(selected_index)
        
        print(f"Attempting to connect to selected host: {friendly_name}")
        
        # Retrieve the ServiceInfo object using the friendly name
        service_info = self.discovered_services.get(friendly_name)
        
        if not service_info:
            self.status_label.config(text=f"Error: Could not find details for {friendly_name}.")
            print(f"Connect failed: ServiceInfo not found for {friendly_name}.")
            return
            
        try:
            # --- Extract info from ServiceInfo --- 
            # Prefer IPv4 if available
            host_addresses = service_info.parsed_addresses()
            host_ip = host_addresses[0] if host_addresses else None
            stream_port = service_info.port
            
            if not host_ip or not stream_port:
                 raise ValueError("ServiceInfo is missing IP address or port.")
                 
            control_port = stream_port + CONTROL_PORT_OFFSET
            print(f"Connecting to {friendly_name} at {host_ip}:{stream_port} (Ctrl: {control_port})")
            # --- End Extract --- 
            
            connected_stream = False
            connected_control = False
        
            # --- Connect sockets using retrieved IP/Port --- 
            self.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.stream_socket.settimeout(5)
            self.stream_socket.connect((host_ip, stream_port))
            self.stream_socket.settimeout(None)
            connected_stream = True
            print("Stream socket connected.")
            # --- Receive Dimensions --- 
            print(f"[*] Receiving stream dimensions from {host_ip}:{stream_port}...")
            try:
                # Set a timeout for receiving dimensions
                self.stream_socket.settimeout(5.0) 
                
                size_data = self.stream_socket.recv(4)
                if not size_data or len(size_data) < 4:
                     raise ValueError("Did not receive dimension size data from host.")
                msg_len = struct.unpack('>I', size_data)[0]
                print(f"[*] Expected dimension JSON size: {msg_len} bytes")
                
                # Limit message size to prevent memory issues
                if msg_len > 4096: 
                     raise ValueError(f"Dimension message size too large: {msg_len}")
                
                dims_json_bytes = self.stream_socket.recv(msg_len)
                if not dims_json_bytes or len(dims_json_bytes) < msg_len:
                     raise ValueError("Did not receive complete dimension JSON data from host.")
                     
                dims_json = dims_json_bytes.decode('utf-8')
                dims = json.loads(dims_json)
                
                # Validate and store dimensions
                new_width = dims.get('width')
                new_height = dims.get('height')
                if not isinstance(new_width, int) or not isinstance(new_height, int) or new_width <= 0 or new_height <= 0:
                     raise ValueError(f"Invalid dimensions received: w={new_width}, h={new_height}")
                     
                self.stream_width = new_width
                self.stream_height = new_height
                self.stream_format = dims.get('format', 'jpeg') # Get format, default to jpeg
                print(f"[*] Received and set stream dimensions: {self.stream_width}x{self.stream_height}, Format: {self.stream_format}")
                
                # Reset timeout for regular stream
                self.stream_socket.settimeout(None) 
                
            except (socket.timeout, struct.error, json.JSONDecodeError, ValueError, ConnectionResetError, BrokenPipeError, OSError) as dim_e:
                 print(f"[ERROR] Failed to receive/parse dimensions: {dim_e}. Using defaults.")
                 self.stream_width = 500 # Fallback to default
                 self.stream_height = 500 # Fallback to default
                 self.stream_socket.settimeout(None) # Ensure timeout is reset
                 # Decide if we should still proceed or close connection?
                 # For now, proceed with defaults, but close if essential data missing.
                 if not size_data or not dims_json_bytes: 
                      self.close_sockets()
                      self.status_label.config(text="Error: Failed receiving host settings.")
                      return
            # --- End Receive Dimensions ---

            # Connect control socket
            print(f"Connecting control to {host_ip}:{control_port}...")
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(5)
            self.control_socket.connect((host_ip, control_port))
            self.control_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.control_socket.settimeout(None)
            connected_control = True
            print("Control socket connected.")
            
            # If both connected successfully
            self.running = True
            self.connected = True
            self.status_label.config(text=f"Connected to {friendly_name} ({host_ip}:{stream_port}) Size:{self.stream_width}x{self.stream_height}, Format: {self.stream_format}") # Update status
            self.connect_button.config(state="disabled")
            self.disconnect_button.config(state="normal")
            self.manual_connect_button.config(state="disabled")
            self.service_listbox.config(state="disabled") # Disable list while connected
            self.save_last_ip(host_ip) # Save the IP used
            self.create_stream_window()
            # --- Start background thread --- 
            threading.Thread(target=self.receive_stream, daemon=True).start()
            # --- Kick off the first UI update --- 
            if self.update_id: # Cancel previous if any (belt-and-suspenders)
                 try: self.root.after_cancel(self.update_id)
                 except: pass
            # Start update frame directly
            self.root.after(100, self.update_frame)
            
        except (ValueError, socket.timeout, ConnectionRefusedError, OSError, Exception) as e:
            error_msg = f"Error connecting to {friendly_name}: {str(e)}"
            print(error_msg)
            self.status_label.config(text=error_msg)
            self.close_sockets()

    def update_frame(self):
        """Updates the canvas with the latest image from the queue. Called from main thread."""
        # Force update stats at least every second even if frames aren't displaying
        current_time = time.time()
        if current_time - self.stats_last_update >= self.stats_update_interval:
            # Force update stats even if we don't display a frame
            self.update_statistics()
            
        if not self.connected or self.stream_window is None or not self.stream_window.winfo_exists():
             self.update_id = None # Ensure no rescheduling if exited
             return 
             
        try:
            latest_img = None
            processed_count = 0
            process_start_time = time.time()
            
            # Get queue status
            queue_size = self.image_queue.qsize()
            queue_fullness = queue_size / self.image_queue.maxsize
            
            # Determine batch size based on queue status
            if self.unlimited_frame_rate.get():
                if queue_fullness > 0.8:
                    # Queue is getting full, grab more frames
                    batch_size = min(20, queue_size // 2)  # Process up to half the queue in one go
                elif queue_fullness > 0.5:
                    # Queue moderately full
                    batch_size = 8
                else:
                    # Normal operation
                    batch_size = 4
            else:
                # Limited FPS mode - just process 1 frame
                batch_size = 1
                
            # Get frames in batches (more efficient than one at a time)
            frames = []
            for _ in range(min(batch_size, queue_size)):
                try:
                    img = self.image_queue.get_nowait()
                    frames.append(img)
                    processed_count += 1
                except queue.Empty:
                    break
                    
            # Update stats regardless of whether we render or not
            self.stats['frames_displayed'] += processed_count
            self.stats['interval_frames_displayed'] += processed_count
                    
            # Use the most recent frame only
            if frames:
                latest_img = frames[-1]
                
            if latest_img:
                try:
                    # Fast-path: Skip conversion if already in right format
                    if latest_img.mode not in ['RGB', 'RGBA']:
                        latest_img = latest_img.convert('RGB')
                    
                    # Create PhotoImage - this is the slow part
                    try:
                        # Try standard approach first
                        self.tk_image = ImageTk.PhotoImage(image=latest_img)
                    except Exception as img_err:
                        print(f"Standard PhotoImage creation failed: {img_err}, trying alternate method")
                        # Try again using a different approach for Parsec/remote desktop compatibility
                        # Convert to a format more compatible with remote desktop solutions
                        img_data = latest_img.tobytes()
                        self.tk_image = tk.PhotoImage(width=latest_img.width, height=latest_img.height)
                        self.tk_image.put(img_data, to=(0, 0, latest_img.width-1, latest_img.height-1))
                    
                    # Minimize canvas operations
                    if self.canvas_image_item is None:
                        # First frame
                        self.canvas_image_item = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
                    else:
                        # Update existing item (faster than delete+create)
                        self.canvas.itemconfig(self.canvas_image_item, image=self.tk_image)
                    
                    # Keep the reference to prevent garbage collection
                    self.canvas.tk_image = self.tk_image
                    
                    # Force canvas to update immediately
                    self.canvas.update_idletasks()
                    
                    # Only resize very occasionally
                    if processed_count % 300 == 0:
                        canvas_width = self.canvas.winfo_width()
                        canvas_height = self.canvas.winfo_height()
                        img_width, img_height = latest_img.size
                        
                        if canvas_width != img_width or canvas_height != img_height:
                            self.canvas.config(width=img_width, height=img_height)
                            self.stream_window.geometry(f"{img_width}x{img_height}+0+0")
                    
                    # Track processing time (only once per batch)
                    process_end_time = time.time()
                    process_time = process_end_time - process_start_time
                    self.stats['processing_times'].append(process_time)
                    if process_time > self.stats['max_processing_time']:
                        self.stats['max_processing_time'] = process_time
                    
                except Exception as render_e:
                    print(f"[Error] Render failure: {render_e}")
                    import traceback
                    traceback.print_exc()
                    self.canvas_image_item = None
            
        except Exception as e:
            print(f"[ERROR] Update frame error: {e}")
            import traceback
            traceback.print_exc()
            
        # Schedule next update based on mode
        if self.running:
            if self.unlimited_frame_rate.get():
                # For unlimited mode, use minimal delay but avoid starving system
                if queue_fullness > 0.5:
                    # Queue filling up, go to max speed
                    self.update_id = self.root.after_idle(self.update_frame)
                else:
                    # Small delay to prevent CPU overload
                    self.update_id = self.root.after(1, self.update_frame)
            else:
                # This should never happen with our changes
                self.update_id = self.root.after(16, self.update_frame)
        else:
            self.update_id = None

    def receive_stream(self):
        frame_count = 0 # Simple frame counter for logging
        log_interval = 100 # Log every 100 frames
        try:
            print("[Stream Thread] Started successfully")
            while self.running:
                try:
                    # Get frame size
                    size_data = self.stream_socket.recv(4)
                    if not size_data:
                        print("[Stream Thread] Connection closed")
                        break
                    size = int.from_bytes(size_data, byteorder='big')
                    if size <= 0:
                        continue
                    
                    # Receive frame data in chunks efficiently
                    data = b''
                    while len(data) < size:
                        bytes_remaining = size - len(data)
                        packet = self.stream_socket.recv(min(4096, bytes_remaining))
                        if not packet:
                            self.running = False
                            break 
                        data += packet
                    if not self.running: break
                    if len(data) != size:
                        continue

                    # Decode frame
                    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        continue
                    
                    # Convert to PIL Image
                    image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(image)
                    
                    # Track received frame
                    self.stats['frames_received'] += 1
                    self.stats['interval_frames_received'] += 1
                    
                    # Queue management for optimal performance
                    queue_size = self.image_queue.qsize()
                    queue_capacity = self.image_queue.maxsize
                    queue_fullness = queue_size / queue_capacity
                    
                    # Advanced queue management strategy
                    if queue_fullness > 0.9:
                        # Critical queue pressure: prioritize newest frames
                        if queue_fullness > 0.95:
                            # Queue almost full - very aggressive dropping
                            # Skip half the frames or keep only every 3rd frame
                            if frame_count % 3 != 0:
                                self.stats['frames_dropped'] += 1
                                frame_count += 1
                                continue
                            
                            # Clear several old frames to relieve pressure
                            frames_to_clear = min(5, queue_size // 2)
                            for _ in range(frames_to_clear):
                                try:
                                    self.image_queue.get_nowait()
                                    self.stats['frames_dropped'] += 1
                                except queue.Empty:
                                    break
                        else:
                            # Queue very full but not critical - moderate dropping
                            # Skip every other frame
                            if frame_count % 2 == 0:
                                self.stats['frames_dropped'] += 1
                                frame_count += 1
                                continue
                            
                            # Clear a couple old frames
                            for _ in range(2):
                                try:
                                    self.image_queue.get_nowait()
                                    self.stats['frames_dropped'] += 1
                                except queue.Empty:
                                    break
                    
                    # Add frame to queue
                    try:
                        self.image_queue.put_nowait(image)
                        frame_count += 1
                    except queue.Full:
                        # Queue full despite management, force add
                        try:
                            self.image_queue.get_nowait()  # Remove oldest
                            self.image_queue.put_nowait(image)
                            self.stats['frames_dropped'] += 1
                            frame_count += 1
                        except:
                            self.stats['frames_dropped'] += 1
                    
                    # Occasional logging
                    if frame_count % log_interval == 0:
                        print(f"[Stream] Received {frame_count} frames, Queue: {queue_size}/{queue_capacity} ({queue_fullness:.0%})")

                except socket.timeout:
                    continue 
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError) as e:
                    if self.running:
                        print(f"[Stream] Connection error: {e}")
                        try:
                            if self.root and self.root.winfo_exists():
                                self.root.after(0, lambda msg=f"Connection error: {e}": 
                                               self.status_label.config(text=msg))
                        except:
                            pass
                    break 
                except Exception as e:
                    if self.running: 
                        print(f"[Stream] Error: {e}")
                    break
                    
        except Exception as e:
            if self.running: 
                print(f"[Stream] Fatal error: {e}")
            try:
                if self.root and self.root.winfo_exists():
                    self.root.after(0, lambda msg=f"Fatal error: {e}": 
                                   self.status_label.config(text=msg))
            except:
                pass
        finally:
            print(f"[Stream] Exiting, processed {frame_count} frames")

    def stop(self):
        print("Stopping client...")
        # --- Cancel pending update --- 
        if self.update_id:
            try:
                self.root.after_cancel(self.update_id)
                print("Cancelled pending UI update.")
            except tk.TclError:
                print("Warning: TclError cancelling UI update (already cancelled/destroyed?).")
            except Exception as e:
                 print(f"Error cancelling UI update: {e}")
            self.update_id = None
        # --- End Cancel --- 
        self.running = False
        self.connected = False
        if hasattr(self, 'stream_socket'):
            try:
                self.stream_socket.close()
            except:
                pass
        if hasattr(self, 'control_socket'):
            try:
                self.control_socket.close()
            except Exception as e:
                print(f"Error closing control server socket in stop(): {e}")
                pass
        self.zeroconf.close()
        
        # Reset performance statistics
        self.reset_statistics()
        
        # Update UI in main thread
        self._update_ui_after_stop()
        
    def _update_ui_after_stop(self):
        """Update UI elements after stopping (called from main thread)"""
        try:
            print("Updating UI after stop...")
            if self.root.winfo_exists(): # Check if root exists
                self.status_label.config(text="Status: Disconnected")
                self.connect_button.config(state="normal")
                self.disconnect_button.config(state="disabled")
                self.manual_connect_button.config(state="normal")
            
            # Hide stream window if it exists
            if self.stream_window and self.stream_window.winfo_exists():
                self.stream_window.withdraw()
            
            # Re-enable listbox
            if hasattr(self, 'service_listbox') and self.service_listbox.winfo_exists():
                 self.service_listbox.config(state="normal")
            # Update connect button state based on selection
            self.on_service_select()
        except tk.TclError as e:
             print(f"_update_ui_after_stop: TclError updating discovery UI: {e}")
        except Exception as e:
             print(f"_update_ui_after_stop: Error updating discovery UI: {e}")
             pass
            
    def manual_connect(self):
        """Connect to host using manually entered IP and port"""
        try:
            host = self.ip_entry.get()
            port = int(self.port_entry.get())
            
            connected_stream = False
            connected_control = False
        
            # Connect stream socket
            print(f"Connecting stream to {host}:{port}...")
            self.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.stream_socket.settimeout(5)
            self.stream_socket.connect((host, port))
            self.stream_socket.settimeout(None)
            connected_stream = True
            print("Stream socket connected.")

            # --- Receive Dimensions (Identical logic as in connect_to_host) ---
            print(f"[*] Receiving stream dimensions from {host}:{port}...")
            try:
                self.stream_socket.settimeout(5.0)
                size_data = self.stream_socket.recv(4)
                if not size_data or len(size_data) < 4: raise ValueError("No dim size")
                msg_len = struct.unpack('>I', size_data)[0]
                if msg_len > 4096: raise ValueError(f"Dim size too large: {msg_len}")
                dims_json_bytes = self.stream_socket.recv(msg_len)
                if not dims_json_bytes or len(dims_json_bytes) < msg_len: raise ValueError("No dim json")
                dims_json = dims_json_bytes.decode('utf-8')
                dims = json.loads(dims_json)
                new_width = dims.get('width')
                new_height = dims.get('height')
                if not isinstance(new_width, int) or not isinstance(new_height, int) or new_width <= 0 or new_height <= 0:
                     raise ValueError(f"Invalid dims: w={new_width}, h={new_height}")
                self.stream_width = new_width
                self.stream_height = new_height
                self.stream_format = dims.get('format', 'jpeg') # Get format, default to jpeg
                print(f"[*] Received and set stream dimensions: {self.stream_width}x{self.stream_height}, Format: {self.stream_format}")
                self.stream_socket.settimeout(None)
            except (socket.timeout, struct.error, json.JSONDecodeError, ValueError, ConnectionResetError, BrokenPipeError, OSError) as dim_e:
                 print(f"[ERROR] Failed to receive/parse dimensions: {dim_e}. Using defaults.")
                 self.stream_width = 500
                 self.stream_height = 500
                 self.stream_socket.settimeout(None)
                 if not size_data or not dims_json_bytes:
                     self.close_sockets()
                     self.status_label.config(text="Error: Failed receiving host settings.")
                     return
            # --- End Receive Dimensions ---

            # Connect control socket
            control_port = port + CONTROL_PORT_OFFSET
            print(f"Connecting control to {host}:{control_port}...")
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(5)
            self.control_socket.connect((host, control_port))
            self.control_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.control_socket.settimeout(None)
            connected_control = True
            print("Control socket connected.")

            # If both connected successfully
            self.running = True
            self.connected = True
            self.status_label.config(text=f"Connected to {host}:{port} (Ctrl:{control_port}, Size:{self.stream_width}x{self.stream_height}, Format: {self.stream_format})")
            self.connect_button.config(state="disabled")
            self.disconnect_button.config(state="normal")
            self.manual_connect_button.config(state="disabled")
            self.service_listbox.config(state="disabled")
            self.save_last_ip(host)
            self.create_stream_window()
            # --- Start background thread --- 
            threading.Thread(target=self.receive_stream, daemon=True).start()
            # --- Kick off the first UI update --- 
            if self.update_id: # Cancel previous if any
                 try: self.root.after_cancel(self.update_id)
                 except: pass
            # Start update frame directly
            self.root.after(100, self.update_frame)
            
        except socket.timeout:
            self.status_label.config(text=f"Error: Connection timed out ({host}:{port if not connected_stream else control_port})")
            self.close_sockets()
        except ConnectionRefusedError:
            self.status_label.config(text=f"Error: Connection refused ({host}:{port if not connected_stream else control_port})")
            self.close_sockets()
        except ValueError:
             self.status_label.config(text="Error: Invalid Port Number")
             self.close_sockets()
        except Exception as e:
            self.status_label.config(text=f"Error connecting: {str(e)}")
            self.close_sockets()
            
    def close_sockets(self):
        """Safely close both stream and control sockets."""
        print("Closing sockets...")
        if self.stream_socket:
            try:
                self.stream_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass # Ignore if already closed
            finally:
                 self.stream_socket.close()
                 self.stream_socket = None
        if self.control_socket:
            try:
                self.control_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                 pass # Ignore if already closed
            finally:
                self.control_socket.close()
                self.control_socket = None
        self.connected = False
        print("Sockets closed.")

    def on_closing(self):
        """Handle window closing"""
        print("Closing application initiated...")
        # --- Cancel pending update --- 
        if self.update_id:
            try:
                self.root.after_cancel(self.update_id)
                print("Cancelled pending UI update on closing.")
            except tk.TclError: pass # Ignore if window already gone
            except Exception as e:
                 print(f"Error cancelling UI update on closing: {e}")
            self.update_id = None
        # --- End Cancel --- 
        
        self.running = False 
        
        # Try to update status one last time before closing
        try:
            if self.root.winfo_exists():
                self.status_label.config(text="Status: Closing...")
        except tk.TclError:
            print("Warning: Could not update status label during closing.")
            
        # Perform cleanup (sockets, zeroconf)
        self.cleanup()
        
        # Explicitly stop the frame update loop if it's still scheduled
        # (Might not be strictly necessary due to self.running=False, but safer)
        if hasattr(self, '_update_frame_after_id'):
            self.root.after_cancel(self._update_frame_after_id)
            
        # Destroy windows (check existence first)
        print("Destroying windows...")
        try:
            if self.stream_window and self.stream_window.winfo_exists():
                self.stream_window.destroy()
        except tk.TclError:
            pass # Ignore error if already destroyed
            
        try:
            if self.root.winfo_exists():
                self.root.destroy()
        except tk.TclError:
            pass # Ignore error if already destroyed

    def cleanup(self):
        """Cleanup non-Tkinter resources"""
        print("Cleaning up non-Tkinter resources...")
        self.close_sockets() # Ensure sockets are closed
        try:
            print("Closing Zeroconf...")
            self.zeroconf.close() # Close Zeroconf instance
        except Exception as e:
            print(f"Error closing Zeroconf: {e}")
            pass
        # Don't cancel browser here, Zeroconf.close() handles it
        # if hasattr(self, 'browser'):
        #    self.browser.cancel()
        print("Cleanup finished.")
        
    def start(self):
        """Start the client application"""
        try:
            # Start GUI
            print("Starting main loop...")
            self.root.mainloop()
            print("Main loop finished.")
        except Exception as e:
            print(f"Error in main loop: {e}")
        finally:
            # Cleanup might have already been called by on_closing
            if self.running: # Check if still running (e.g., mainloop crashed)
               print("Main loop exited unexpectedly, ensuring cleanup...")
               self.on_closing() # Call the proper closing sequence

    def on_service_select(self, event=None):
        """Handle selection change in the service listbox."""
        selection_indices = self.service_listbox.curselection()
        if selection_indices: # If something is selected
             self.connect_button.config(state="normal")
        else:
             self.connect_button.config(state="disabled")

    def update_service_list(self):
        """Update the listbox display with discovered service names."""
        # Ensure Listbox exists
        if not hasattr(self, 'service_listbox') or not self.service_listbox.winfo_exists(): 
            # print("Update Service List: UI not ready (Listbox)")
            return 
        
        service_names = list(self.discovered_services.keys())
        # print(f"Updating service list display: {service_names}")
        self.discovered_list_var.set(service_names)
        
        # --- Ensure Connect Button exists before configuring --- 
        if hasattr(self, 'connect_button'):
             if service_names:
                  self.connect_button.config(state="normal") 
             else:
                  self.connect_button.config(state="disabled")
        # else: # Debug log
             # print("Update Service List: Connect button not found yet.")
        # --- End Check --- 

    def reset_statistics(self):
        """Reset all performance statistics."""
        now = time.time()
        self.stats = {
            'frames_received': 0,           # Total frames received 
            'frames_displayed': 0,          # Total frames displayed
            'frames_dropped': 0,            # Total frames dropped
            'last_stats_reset': now,
            'fps_received': 0.0,            # Current receiving FPS
            'fps_displayed': 0.0,           # Current displaying FPS
            'processing_times': [],         # List to calculate average processing time
            'max_processing_time': 0.0,
            'queue_max_size': 30,           # Should match the queue size
            # New interval tracking
            'interval_frames_received': 0,  # Frames received in current interval
            'interval_frames_displayed': 0, # Frames displayed in current interval
            'last_interval_time': now       # Last interval start time
        }
        self.stats_last_update = now
        
        # Update UI to show reset stats
        self.update_statistics_display()
        
    def update_statistics(self):
        """Calculate and update performance statistics."""
        if not self.connected:
            return
            
        now = time.time()
        elapsed = now - self.stats_last_update
        
        # Only update at the specified interval
        if elapsed < self.stats_update_interval:
            return
            
        # Calculate FPS based on interval frames
        interval_elapsed = now - self.stats['last_interval_time']
        if interval_elapsed > 0:
            # Calculate current FPS based only on this interval
            self.stats['fps_received'] = self.stats['interval_frames_received'] / interval_elapsed
            self.stats['fps_displayed'] = self.stats['interval_frames_displayed'] / interval_elapsed
            
            # Reset interval counters
            self.stats['interval_frames_received'] = 0
            self.stats['interval_frames_displayed'] = 0
            self.stats['last_interval_time'] = now
        
        # Calculate average processing time (if we have any data)
        if self.stats['processing_times']:
            # Take only the last 100 processing times to avoid growing unbounded
            self.stats['processing_times'] = self.stats['processing_times'][-100:]
            avg_time = sum(self.stats['processing_times']) / len(self.stats['processing_times'])
            self.stats['avg_processing_time'] = avg_time
        
        # Update the UI with new statistics
        self.update_statistics_display()
        
        # Reset the update timer
        self.stats_last_update = now
        
    def update_statistics_display(self):
        """Update the UI with current statistics."""
        try:
            # Format the statistics for display
            self.fps_received_label.config(text=f"{self.stats['fps_received']:.1f} FPS")
            self.fps_displayed_label.config(text=f"{self.stats['fps_displayed']:.1f} FPS")
            
            self.frames_dropped_label.config(text=str(self.stats['frames_dropped']))
            
            queue_size = self.image_queue.qsize()
            queue_percent = (queue_size / self.stats['queue_max_size']) * 100
            self.queue_usage_label.config(text=f"{queue_percent:.0f}%")
            
            if 'avg_processing_time' in self.stats:
                avg_ms = self.stats['avg_processing_time'] * 1000
                self.avg_processing_label.config(text=f"{avg_ms:.1f} ms")
            
            max_ms = self.stats['max_processing_time'] * 1000
            self.max_processing_label.config(text=f"{max_ms:.1f} ms")
        except (tk.TclError, AttributeError) as e:
            # Ignore errors if UI elements don't exist yet or anymore
            pass

if __name__ == "__main__":
    client = None # Initialize client to None
    try:
        print("Creating ScreenShareClient...")
        client = ScreenShareClient()
        print("Starting client...")
        client.start()
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected...")
    except Exception as e:
        print(f"Unhandled error in main execution: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for unexpected errors
    finally:
        print("Application exit sequence starting...")
        if client and client.running:
             print("Performing final cleanup via on_closing...")
             client.on_closing() # Ensure cleanup happens if start() exited prematurely
        elif client:
             print("Cleanup likely already performed by on_closing.")
        else:
             print("Client object not created.")
        print("Exiting application.")
        # sys.exit(0) # Removed force exit, let Python exit normally after cleanup