import os
import subprocess
import sys

def build_executable(script_name, output_name):
    print(f"Building {output_name}...")
    
    # PyInstaller command
    cmd = [
        'pyinstaller',
        '--name', output_name,
        '--onefile',  # Create a single executable
        '--windowed',  # Don't show console window
        '--icon', 'icon.ico' if os.path.exists('icon.ico') else None,
        '--add-data', 'icon.ico;.' if os.path.exists('icon.ico') else None,
        '--clean',  # Clean PyInstaller cache
        script_name
    ]
    
    # Remove None values
    cmd = [x for x in cmd if x is not None]
    
    # Run PyInstaller
    subprocess.run(cmd, check=True)
    
    print(f"Finished building {output_name}")

def main():
    # Create dist directory if it doesn't exist
    if not os.path.exists('dist'):
        os.makedirs('dist')
    
    # Build host executable
    build_executable('host.py', 'ScreenShareHost')
    
    # Build client executable
    build_executable('client.py', 'ScreenShareClient')
    
    print("\nBuild complete! Executables are in the 'dist' directory.")
    print("You can create shortcuts to these executables.")

if __name__ == "__main__":
    main() 