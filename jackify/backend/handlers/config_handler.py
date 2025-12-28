#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Handler Module
Handles application settings and configuration
"""

import os
import json
import logging
import shutil
import re
import base64
import hashlib
from pathlib import Path
from typing import Optional

# Initialize logger
logger = logging.getLogger(__name__)


class ConfigHandler:
    """
    Handles application configuration and settings
    Singleton pattern ensures all code shares the same instance
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigHandler, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize configuration handler with default settings"""
        # Only initialize once (singleton pattern)
        if ConfigHandler._initialized:
            return
        ConfigHandler._initialized = True

        self.config_dir = os.path.expanduser("~/.config/jackify")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.settings = {
            "version": "0.2.0",
            "last_selected_modlist": None,
            "steam_libraries": [],
            "resolution": None,
            "protontricks_path": None,
            "steam_path": None,
            "nexus_api_key": None,  # Base64 encoded API key
            "default_install_parent_dir": None,  # Parent directory for modlist installations
            "default_download_parent_dir": None,  # Parent directory for downloads
            "modlist_install_base_dir": os.path.expanduser("~/Games"),  # Configurable base directory for modlist installations
            "modlist_downloads_base_dir": os.path.expanduser("~/Games/Modlist_Downloads"),  # Configurable base directory for downloads
            "jackify_data_dir": None,  # Configurable Jackify data directory (default: ~/Jackify)
            "use_winetricks_for_components": True,  # DEPRECATED: Migrated to component_installation_method. Kept for backward compatibility.
            "component_installation_method": "winetricks",  # "winetricks" (default) or "system_protontricks"
            "game_proton_path": None,  # Proton version for game shortcuts (can be any Proton 9+), separate from install proton
            "steam_restart_strategy": "jackify",  # "jackify" (default) or "nak_simple"
            "window_width": None,  # Saved window width (None = use dynamic sizing)
            "window_height": None  # Saved window height (None = use dynamic sizing)
        }
        
        # Load configuration if exists
        self._load_config()

        # Perform version migrations
        self._migrate_config()

        # If steam_path is not set, detect it
        if not self.settings["steam_path"]:
            self.settings["steam_path"] = self._detect_steam_path()

        # Auto-detect and set Proton version ONLY on first run (config file doesn't exist)
        # Do NOT overwrite user's saved settings!
        if not os.path.exists(self.config_file) and not self.settings.get("proton_path"):
            self._auto_detect_proton()
        
        # If jackify_data_dir is not set, initialize it to default
        if not self.settings.get("jackify_data_dir"):
            self.settings["jackify_data_dir"] = os.path.expanduser("~/Jackify")
            # Save the updated settings
            self.save_config()
    
    def _detect_steam_path(self):
        """
        Detect the Steam installation path
        
        Returns:
            str: Path to the Steam installation or None if not found
        """
        logger.info("Detecting Steam installation path...")
        
        # Common Steam installation paths
        steam_paths = [
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.local/share/Steam"),
            os.path.expanduser("~/.steam/root")
        ]
        
        # Check each path
        for path in steam_paths:
            if os.path.exists(path):
                logger.info(f"Found Steam installation at: {path}")
                return path
        
        # If not found in common locations, try to find using libraryfolders.vdf
        libraryfolders_vdf_paths = [
            os.path.expanduser("~/.steam/steam/config/libraryfolders.vdf"),
            os.path.expanduser("~/.local/share/Steam/config/libraryfolders.vdf"),
            os.path.expanduser("~/.steam/root/config/libraryfolders.vdf"),
            os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/config/libraryfolders.vdf")  # Flatpak
        ]
        
        for vdf_path in libraryfolders_vdf_paths:
            if os.path.exists(vdf_path):
                # Extract the Steam path from the libraryfolders.vdf path
                steam_path = os.path.dirname(os.path.dirname(vdf_path))
                logger.info(f"Found Steam installation at: {steam_path}")
                return steam_path
        
        logger.error("Steam installation not found")
        return None
    
    def _load_config(self):
        """
        Load configuration from file and update in-memory cache.
        For legacy compatibility with initialization code.
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    saved_config = json.load(f)
                    # Update settings with saved values while preserving defaults
                    self.settings.update(saved_config)
                    logger.debug("Loaded configuration from file")
            else:
                logger.debug("No configuration file found, using defaults")
                self._create_config_dir()
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")

    def _migrate_config(self):
        """
        Migrate configuration between versions
        Handles breaking changes and data format updates
        """
        current_version = self.settings.get("version", "0.0.0")
        target_version = "0.2.0"

        if current_version == target_version:
            return

        logger.info(f"Migrating config from {current_version} to {target_version}")

        # Migration: v0.0.x -> v0.2.0
        # Encryption changed from cryptography (Fernet) to pycryptodome (AES-GCM)
        # Old encrypted API keys cannot be decrypted, must be re-entered
        from packaging import version
        if version.parse(current_version) < version.parse("0.2.0"):
            # Clear old encrypted credentials
            if self.settings.get("nexus_api_key"):
                logger.warning("Clearing saved API key due to encryption format change")
                logger.warning("Please re-enter your Nexus API key in Settings")
                self.settings["nexus_api_key"] = None

            # Clear OAuth token file (different encryption format)
            oauth_token_file = Path(self.config_dir) / "nexus-oauth.json"
            if oauth_token_file.exists():
                logger.warning("Clearing saved OAuth token due to encryption format change")
                logger.warning("Please re-authorize with Nexus Mods")
                try:
                    oauth_token_file.unlink()
                except Exception as e:
                    logger.error(f"Failed to remove old OAuth token: {e}")

            # Remove obsolete keys
            obsolete_keys = [
                "hoolamike_install_path",
                "hoolamike_version",
                "api_key_fallback_enabled",
                "proton_version",  # Display string only, path stored in proton_path
                "game_proton_version"  # Display string only, path stored in game_proton_path
            ]

            removed_count = 0
            for key in obsolete_keys:
                if key in self.settings:
                    del self.settings[key]
                    removed_count += 1

            if removed_count > 0:
                logger.info(f"Removed {removed_count} obsolete config keys")

            # Update version
            self.settings["version"] = target_version
            self.save_config()
            logger.info("Config migration completed")

    def _read_config_from_disk(self):
        """
        Read configuration directly from disk without caching.
        Returns merged config (defaults + saved values).
        """
        try:
            config = self.settings.copy()  # Start with defaults
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    saved_config = json.load(f)
                    config.update(saved_config)
            return config
        except Exception as e:
            logger.error(f"Error reading configuration from disk: {e}")
            return self.settings.copy()

    def reload_config(self):
        """Reload configuration from disk to pick up external changes"""
        self._load_config()
    
    def _create_config_dir(self):
        """Create configuration directory if it doesn't exist"""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            logger.debug(f"Created configuration directory: {self.config_dir}")
        except Exception as e:
            logger.error(f"Error creating configuration directory: {e}")
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            self._create_config_dir()
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            logger.debug("Saved configuration to file")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def get(self, key, default=None):
        """
        Get a configuration value by key.
        Always reads fresh from disk to avoid stale data.
        """
        config = self._read_config_from_disk()
        return config.get(key, default)
    
    def set(self, key, value):
        """Set a configuration value"""
        self.settings[key] = value
        return True
    
    def update(self, settings_dict):
        """Update multiple configuration values"""
        self.settings.update(settings_dict)
        return True
    
    def add_steam_library(self, path):
        """Add a Steam library path to configuration"""
        if path not in self.settings["steam_libraries"]:
            self.settings["steam_libraries"].append(path)
            logger.debug(f"Added Steam library: {path}")
            return True
        return False
    
    def remove_steam_library(self, path):
        """Remove a Steam library path from configuration"""
        if path in self.settings["steam_libraries"]:
            self.settings["steam_libraries"].remove(path)
            logger.debug(f"Removed Steam library: {path}")
            return True
        return False
    
    def set_resolution(self, width, height):
        """Set preferred resolution"""
        resolution = f"{width}x{height}"
        self.settings["resolution"] = resolution
        logger.debug(f"Set resolution to: {resolution}")
        return True
    
    def get_resolution(self):
        """Get preferred resolution"""
        return self.settings.get("resolution")
    
    def set_last_modlist(self, modlist_name):
        """Save the last selected modlist"""
        self.settings["last_selected_modlist"] = modlist_name
        logger.debug(f"Set last selected modlist to: {modlist_name}")
        return True
    
    def get_last_modlist(self):
        """Get the last selected modlist"""
        return self.settings.get("last_selected_modlist")
    
    def set_protontricks_path(self, path):
        """Set the path to protontricks executable"""
        self.settings["protontricks_path"] = path
        logger.debug(f"Set protontricks path to: {path}")
        return True
    
    def get_protontricks_path(self):
        """Get the path to protontricks executable"""
        return self.settings.get("protontricks_path") 
    
    def _get_encryption_key(self) -> bytes:
        """
        Generate encryption key for API key storage using same method as OAuth tokens

        Returns:
            Fernet-compatible encryption key
        """
        import socket
        import getpass

        try:
            hostname = socket.gethostname()
            username = getpass.getuser()

            # Try to get machine ID
            machine_id = None
            try:
                with open('/etc/machine-id', 'r') as f:
                    machine_id = f.read().strip()
            except:
                try:
                    with open('/var/lib/dbus/machine-id', 'r') as f:
                        machine_id = f.read().strip()
                except:
                    pass

            if machine_id:
                key_material = f"{hostname}:{username}:{machine_id}:jackify"
            else:
                key_material = f"{hostname}:{username}:jackify"

        except Exception as e:
            logger.warning(f"Failed to get machine info for encryption: {e}")
            key_material = "jackify:default:key"

        # Generate Fernet-compatible key
        key_bytes = hashlib.sha256(key_material.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(key_bytes)

    def _encrypt_api_key(self, api_key: str) -> str:
        """
        Encrypt API key using AES-GCM

        Args:
            api_key: Plain text API key

        Returns:
            Encrypted API key string
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Random import get_random_bytes

            # Derive 32-byte AES key
            key = base64.urlsafe_b64decode(self._get_encryption_key())

            # Generate random nonce
            nonce = get_random_bytes(12)

            # Encrypt with AES-GCM
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            ciphertext, tag = cipher.encrypt_and_digest(api_key.encode('utf-8'))

            # Combine and encode
            combined = nonce + ciphertext + tag
            return base64.b64encode(combined).decode('utf-8')

        except ImportError:
            # Fallback to base64 if pycryptodome not available
            logger.warning("pycryptodome not available, using base64 encoding (less secure)")
            return base64.b64encode(api_key.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encrypting API key: {e}")
            return ""

    def _decrypt_api_key(self, encrypted_key: str) -> Optional[str]:
        """
        Decrypt API key using AES-GCM

        Args:
            encrypted_key: Encrypted API key string

        Returns:
            Decrypted API key or None on failure
        """
        try:
            from Crypto.Cipher import AES
            
            # Check if MODE_GCM is available (pycryptodome has it, old pycrypto doesn't)
            if not hasattr(AES, 'MODE_GCM'):
                # Fallback to base64 decode if old pycrypto is installed
                try:
                    return base64.b64decode(encrypted_key.encode('utf-8')).decode('utf-8')
                except:
                    return None

            # Derive 32-byte AES key
            key = base64.urlsafe_b64decode(self._get_encryption_key())

            # Decode and split
            combined = base64.b64decode(encrypted_key.encode('utf-8'))
            nonce = combined[:12]
            tag = combined[-16:]
            ciphertext = combined[12:-16]

            # Decrypt with AES-GCM
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)

            return plaintext.decode('utf-8')

        except ImportError:
            # Fallback to base64 decode
            try:
                return base64.b64decode(encrypted_key.encode('utf-8')).decode('utf-8')
            except:
                return None
        except AttributeError:
            # Old pycrypto doesn't have MODE_GCM, fallback to base64
            try:
                return base64.b64decode(encrypted_key.encode('utf-8')).decode('utf-8')
            except:
                return None
        except Exception as e:
            # Might be old base64-only format, try decoding
            try:
                return base64.b64decode(encrypted_key.encode('utf-8')).decode('utf-8')
            except:
                logger.error(f"Error decrypting API key: {e}")
                return None

    def save_api_key(self, api_key):
        """
        Save Nexus API key with Fernet encryption

        Args:
            api_key (str): Plain text API key

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            if api_key:
                # Encrypt the API key using Fernet
                encrypted_key = self._encrypt_api_key(api_key)
                if not encrypted_key:
                    logger.error("Failed to encrypt API key")
                    return False

                self.settings["nexus_api_key"] = encrypted_key
                logger.debug("API key encrypted and saved successfully")
            else:
                # Clear the API key if empty
                self.settings["nexus_api_key"] = None
                logger.debug("API key cleared")

            result = self.save_config()

            # Set restrictive permissions on config file
            if result:
                try:
                    os.chmod(self.config_file, 0o600)
                except Exception as e:
                    logger.warning(f"Could not set restrictive permissions on config: {e}")

            return result

        except Exception as e:
            logger.error(f"Error saving API key: {e}")
            return False

    def get_api_key(self):
        """
        Retrieve and decrypt the saved Nexus API key.
        Always reads fresh from disk.

        Returns:
            str: Decrypted API key or None if not saved
        """
        try:
            config = self._read_config_from_disk()
            encrypted_key = config.get("nexus_api_key")
            if encrypted_key:
                # Decrypt the API key
                decrypted_key = self._decrypt_api_key(encrypted_key)
                return decrypted_key
            return None
        except Exception as e:
            logger.error(f"Error retrieving API key: {e}")
            return None
    
    def has_saved_api_key(self):
        """
        Check if an API key is saved in configuration.
        Always reads fresh from disk.

        Returns:
            bool: True if API key exists, False otherwise
        """
        config = self._read_config_from_disk()
        return config.get("nexus_api_key") is not None
    
    def clear_api_key(self):
        """
        Clear the saved API key from configuration
        
        Returns:
            bool: True if cleared successfully, False otherwise
        """
        try:
            self.settings["nexus_api_key"] = None
            logger.debug("API key cleared from configuration")
            return self.save_config()
        except Exception as e:
            logger.error(f"Error clearing API key: {e}")
            return False
    def save_resolution(self, resolution):
        """
        Save resolution setting to configuration
        
        Args:
            resolution (str): Resolution string (e.g., '1920x1080')
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            if resolution and resolution != 'Leave unchanged':
                self.settings["resolution"] = resolution
                logger.debug(f"Resolution saved: {resolution}")
            else:
                # Clear resolution if 'Leave unchanged' or empty
                self.settings["resolution"] = None
                logger.debug("Resolution cleared")
            
            return self.save_config()
        except Exception as e:
            logger.error(f"Error saving resolution: {e}")
            return False
    
    def get_saved_resolution(self):
        """
        Retrieve the saved resolution from configuration
        
        Returns:
            str: Saved resolution or None if not saved
        """
        try:
            resolution = self.settings.get("resolution")
            if resolution:
                logger.debug(f"Retrieved saved resolution: {resolution}")
            else:
                logger.debug("No saved resolution found")
            return resolution
        except Exception as e:
            logger.error(f"Error retrieving resolution: {e}")
            return None
    
    def has_saved_resolution(self):
        """
        Check if a resolution is saved in configuration
        
        Returns:
            bool: True if resolution exists, False otherwise
        """
        return self.settings.get("resolution") is not None
    
    def clear_saved_resolution(self):
        """
        Clear the saved resolution from configuration
        
        Returns:
            bool: True if cleared successfully, False otherwise
        """
        try:
            self.settings["resolution"] = None
            logger.debug("Resolution cleared from configuration")
            return self.save_config()
        except Exception as e:
            logger.error(f"Error clearing resolution: {e}")
            return False

    def set_default_install_parent_dir(self, path):
        """
        Save the parent directory for modlist installations
        
        Args:
            path (str): Parent directory path to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            if path and os.path.exists(path):
                self.settings["default_install_parent_dir"] = path
                logger.debug(f"Default install parent directory saved: {path}")
                return self.save_config()
            else:
                logger.warning(f"Invalid or non-existent path for install parent directory: {path}")
                return False
        except Exception as e:
            logger.error(f"Error saving install parent directory: {e}")
            return False
    
    def get_default_install_parent_dir(self):
        """
        Retrieve the saved parent directory for modlist installations
        
        Returns:
            str: Saved parent directory path or None if not saved
        """
        try:
            path = self.settings.get("default_install_parent_dir")
            if path and os.path.exists(path):
                logger.debug(f"Retrieved default install parent directory: {path}")
                return path
            else:
                logger.debug("No valid default install parent directory found")
                return None
        except Exception as e:
            logger.error(f"Error retrieving install parent directory: {e}")
            return None
    
    def set_default_download_parent_dir(self, path):
        """
        Save the parent directory for downloads
        
        Args:
            path (str): Parent directory path to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            if path and os.path.exists(path):
                self.settings["default_download_parent_dir"] = path
                logger.debug(f"Default download parent directory saved: {path}")
                return self.save_config()
            else:
                logger.warning(f"Invalid or non-existent path for download parent directory: {path}")
                return False
        except Exception as e:
            logger.error(f"Error saving download parent directory: {e}")
            return False
    
    def get_default_download_parent_dir(self):
        """
        Retrieve the saved parent directory for downloads
        
        Returns:
            str: Saved parent directory path or None if not saved
        """
        try:
            path = self.settings.get("default_download_parent_dir")
            if path and os.path.exists(path):
                logger.debug(f"Retrieved default download parent directory: {path}")
                return path
            else:
                logger.debug("No valid default download parent directory found")
                return None
        except Exception as e:
            logger.error(f"Error retrieving download parent directory: {e}")
            return None
    
    def has_saved_install_parent_dir(self):
        """
        Check if a default install parent directory is saved in configuration
        
        Returns:
            bool: True if directory exists and is valid, False otherwise
        """
        path = self.settings.get("default_install_parent_dir")
        return path is not None and os.path.exists(path)
    
    def has_saved_download_parent_dir(self):
        """
        Check if a default download parent directory is saved in configuration
        
        Returns:
            bool: True if directory exists and is valid, False otherwise
        """
        path = self.settings.get("default_download_parent_dir")
        return path is not None and os.path.exists(path)
    
    def get_modlist_install_base_dir(self):
        """
        Get the configurable base directory for modlist installations
        
        Returns:
            str: Base directory path for modlist installations
        """
        return self.settings.get("modlist_install_base_dir", os.path.expanduser("~/Games"))
    
    def set_modlist_install_base_dir(self, path):
        """
        Set the configurable base directory for modlist installations
        
        Args:
            path (str): Base directory path to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            if path:
                self.settings["modlist_install_base_dir"] = path
                logger.debug(f"Modlist install base directory saved: {path}")
                return self.save_config()
            else:
                logger.warning("Invalid path for modlist install base directory")
                return False
        except Exception as e:
            logger.error(f"Error saving modlist install base directory: {e}")
            return False
    
    def get_modlist_downloads_base_dir(self):
        """
        Get the configurable base directory for modlist downloads
        
        Returns:
            str: Base directory path for modlist downloads
        """
        return self.settings.get("modlist_downloads_base_dir", os.path.expanduser("~/Games/Modlist_Downloads"))
    
    def set_modlist_downloads_base_dir(self, path):
        """
        Set the configurable base directory for modlist downloads
        
        Args:
            path (str): Base directory path to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            if path:
                self.settings["modlist_downloads_base_dir"] = path
                logger.debug(f"Modlist downloads base directory saved: {path}")
                return self.save_config()
            else:
                logger.warning("Invalid path for modlist downloads base directory")
                return False
        except Exception as e:
            logger.error(f"Error saving modlist downloads base directory: {e}")
            return False

    def get_proton_path(self):
        """
        Retrieve the saved Install Proton path from configuration (for jackify-engine).
        Always reads fresh from disk.

        Returns:
            str: Saved Install Proton path or 'auto' if not saved
        """
        try:
            config = self._read_config_from_disk()
            proton_path = config.get("proton_path", "auto")
            logger.debug(f"Retrieved fresh install proton_path from config: {proton_path}")
            return proton_path
        except Exception as e:
            logger.error(f"Error retrieving install proton_path: {e}")
            return "auto"

    def get_game_proton_path(self):
        """
        Retrieve the saved Game Proton path from configuration (for game shortcuts).
        Falls back to install Proton path if game Proton not set.
        Always reads fresh from disk.

        Returns:
            str: Saved Game Proton path, Install Proton path, or 'auto' if not saved
        """
        try:
            config = self._read_config_from_disk()
            game_proton_path = config.get("game_proton_path")

            # If game proton not set or set to same_as_install, use install proton
            if not game_proton_path or game_proton_path == "same_as_install":
                game_proton_path = config.get("proton_path", "auto")

            logger.debug(f"Retrieved fresh game proton_path from config: {game_proton_path}")
            return game_proton_path
        except Exception as e:
            logger.error(f"Error retrieving game proton_path: {e}")
            return "auto"

    def get_proton_version(self):
        """
        Retrieve the saved Proton version from configuration.
        Always reads fresh from disk.

        Returns:
            str: Saved Proton version or 'auto' if not saved
        """
        try:
            config = self._read_config_from_disk()
            proton_version = config.get("proton_version", "auto")
            logger.debug(f"Retrieved fresh proton_version from config: {proton_version}")
            return proton_version
        except Exception as e:
            logger.error(f"Error retrieving proton_version: {e}")
            return "auto"

    def _auto_detect_proton(self):
        """Auto-detect and set best Proton version (includes GE-Proton and Valve Proton)"""
        try:
            from .wine_utils import WineUtils
            best_proton = WineUtils.select_best_proton()

            if best_proton:
                self.settings["proton_path"] = str(best_proton['path'])
                self.settings["proton_version"] = best_proton['name']
                proton_type = best_proton.get('type', 'Unknown')
                logger.info(f"Auto-detected Proton: {best_proton['name']} ({proton_type})")
                self.save_config()
            else:
                # Fallback to auto-detect mode
                self.settings["proton_path"] = "auto"
                self.settings["proton_version"] = "auto"
                logger.info("No compatible Proton versions found, using auto-detect mode")
                self.save_config()

        except Exception as e:
            logger.error(f"Failed to auto-detect Proton: {e}")
            self.settings["proton_path"] = "auto"
            self.settings["proton_version"] = "auto"

 