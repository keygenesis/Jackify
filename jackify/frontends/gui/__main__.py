#!/usr/bin/env python3
"""
Entry point for Jackify GUI Frontend

Usage: python -m jackify.frontends.gui
"""

import sys
from pathlib import Path

def main():
    # Check if launched with jackify:// protocol URL (OAuth callback)
    if len(sys.argv) > 1 and sys.argv[1].startswith('jackify://'):
        handle_protocol_url(sys.argv[1])
        return

    # Normal GUI launch
    from jackify.frontends.gui.main import main as gui_main
    gui_main()

def handle_protocol_url(url: str):
    """Handle jackify:// protocol URL (OAuth callback)"""
    import os
    import sys
    
    # Enhanced logging with system information
    try:
        from jackify.shared.paths import get_jackify_logs_dir
        log_dir = get_jackify_logs_dir()
    except Exception as e:
        # Fallback if config system fails
        log_dir = Path.home() / ".config" / "jackify" / "logs"
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "protocol_handler.log"

    def log(msg):
        with open(log_file, 'a') as f:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {msg}\n")
            f.flush()  # Ensure immediate write

    try:
        # Log system information for debugging
        log(f"=== Protocol Handler Invoked ===")
        log(f"URL: {url}")
        log(f"Python executable: {sys.executable}")
        log(f"Script path: {sys.argv[0]}")
        log(f"Working directory: {os.getcwd()}")
        log(f"APPIMAGE env: {os.environ.get('APPIMAGE', 'Not set')}")
        log(f"APPDIR env: {os.environ.get('APPDIR', 'Not set')}")
        
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        log(f"Parsed URL - scheme: {parsed.scheme}, netloc: {parsed.netloc}, path: {parsed.path}, query: {parsed.query}")
        
        # URL format: jackify://oauth/callback?code=XXX&state=YYY
        # urlparse treats "oauth" as netloc, so reconstruct full path
        full_path = f"/{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
        log(f"Reconstructed path: {full_path}")

        if full_path == '/oauth/callback':
            params = parse_qs(parsed.query)
            code = params.get('code', [None])[0]
            state = params.get('state', [None])[0]
            error = params.get('error', [None])[0]
            
            log(f"OAuth parameters - Code: {'Present' if code else 'Missing'}, State: {'Present' if state else 'Missing'}, Error: {error}")

            if error:
                log(f"ERROR: OAuth error received: {error}")
                error_description = params.get('error_description', ['No description'])[0]
                log(f"ERROR: OAuth error description: {error_description}")
                print(f"OAuth authorization failed: {error} - {error_description}")
            elif code and state:
                # Write to callback file for OAuth service to pick up
                callback_file = Path.home() / ".config" / "jackify" / "oauth_callback.tmp"
                log(f"Creating callback file: {callback_file}")
                
                try:
                    callback_file.parent.mkdir(parents=True, exist_ok=True)
                    callback_content = f"{code}\n{state}"
                    callback_file.write_text(callback_content)
                    
                    # Verify file was written
                    if callback_file.exists():
                        written_content = callback_file.read_text()
                        log(f"Callback file created successfully, size: {len(written_content)} bytes")
                        print("OAuth callback received and saved successfully")
                    else:
                        log("ERROR: Callback file was not created")
                        print("Error: Failed to create callback file")
                        
                except Exception as callback_error:
                    log(f"ERROR: Failed to write callback file: {callback_error}")
                    print(f"Error writing callback file: {callback_error}")
            else:
                log("ERROR: Missing required OAuth parameters (code or state)")
                print("Invalid OAuth callback - missing required parameters")
        else:
            log(f"ERROR: Unknown protocol path: {full_path}")
            print(f"Unknown protocol path: {full_path}")
            
        log("=== Protocol Handler Completed ===")
        
    except Exception as e:
        log(f"CRITICAL EXCEPTION: {e}")
        import traceback
        log(f"TRACEBACK:\n{traceback.format_exc()}")
        print(f"Critical error handling protocol URL: {e}")
        
        # Try to log to a fallback location if main logging fails
        try:
            fallback_log = Path.home() / "jackify_protocol_error.log"
            with open(fallback_log, 'a') as f:
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] CRITICAL ERROR: {e}\n")
                f.write(f"URL: {url}\n")
                f.write(f"Traceback:\n{traceback.format_exc()}\n\n")
        except:
            pass  # If even fallback logging fails, just continue

if __name__ == "__main__":
    main() 