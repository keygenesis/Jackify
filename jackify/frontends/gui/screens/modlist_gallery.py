"""
Enhanced Modlist Gallery Screen for Jackify GUI.

Provides visual browsing, filtering, and selection of modlists using
rich metadata from jackify-engine.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QScrollArea, QGridLayout,
    QFrame, QSizePolicy, QDialog, QTextEdit, QTextBrowser, QMessageBox, QListWidget
)
from PySide6.QtCore import Qt, Signal, QSize, QThread, QUrl, QTimer, QObject
from PySide6.QtGui import QPixmap, QFont, QPainter, QColor, QTextOption, QPalette
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from pathlib import Path
from typing import List, Optional, Dict
from collections import deque
import random

from jackify.backend.services.modlist_gallery_service import ModlistGalleryService
from jackify.backend.models.modlist_metadata import ModlistMetadata, ModlistMetadataResponse
from ..shared_theme import JACKIFY_COLOR_BLUE
from ..utils import get_screen_geometry, set_responsive_minimum


class ImageManager(QObject):
    """Centralized image loading and caching manager"""
    
    def __init__(self, gallery_service: ModlistGalleryService):
        super().__init__()
        self.gallery_service = gallery_service
        self.pixmap_cache: Dict[str, QPixmap] = {}
        self.network_manager = QNetworkAccessManager()
        self.download_queue = deque()
        self.downloading: set = set()
        self.max_concurrent = 2  # Start with 2 concurrent downloads to reduce UI lag
        self.save_queue = deque()  # Queue for deferred disk saves
        self._save_timer = None
        
    def get_image(self, metadata: ModlistMetadata, callback, size: str = "small") -> Optional[QPixmap]:
        """
        Get image for modlist - returns cached pixmap or None if needs download
        
        Args:
            metadata: Modlist metadata
            callback: Callback function when image is loaded
            size: Image size to use ("small" for cards, "large" for detail view)
        """
        cache_key = f"{metadata.machineURL}_{size}"
        
        # Check memory cache first (should be preloaded)
        if cache_key in self.pixmap_cache:
            return self.pixmap_cache[cache_key]
        
        # Only check disk cache if not in memory (fallback for images that weren't preloaded)
        # This should rarely happen if preload worked correctly
        cached_path = self.gallery_service.get_cached_image_path(metadata, size)
        if cached_path and cached_path.exists():
            try:
                pixmap = QPixmap(str(cached_path))
                if not pixmap.isNull():
                    self.pixmap_cache[cache_key] = pixmap
                    return pixmap
            except Exception:
                pass
        
        # Queue for download if not cached
        if cache_key not in self.downloading:
            self.download_queue.append((metadata, callback, size))
            self._process_queue()
        
        return None
    
    def _process_queue(self):
        """Process download queue up to max_concurrent"""
        # Process one at a time with small delays to keep UI responsive
        if len(self.downloading) < self.max_concurrent and self.download_queue:
            metadata, callback, size = self.download_queue.popleft()
            cache_key = f"{metadata.machineURL}_{size}"
            
            if cache_key not in self.downloading:
                self.downloading.add(cache_key)
                self._download_image(metadata, callback, size)
                
                # Schedule next download with small delay to yield to UI
                if self.download_queue:
                    QTimer.singleShot(100, self._process_queue)
    
    def _download_image(self, metadata: ModlistMetadata, callback, size: str = "small"):
        """Download image from network"""
        image_url = self.gallery_service.get_image_url(metadata, size)
        if not image_url:
            cache_key = f"{metadata.machineURL}_{size}"
            self.downloading.discard(cache_key)
            self._process_queue()
            return
        
        url = QUrl(image_url)
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"Jackify/0.1.8")
        
        reply = self.network_manager.get(request)
        reply.finished.connect(lambda: self._on_download_finished(reply, metadata, callback, size))
    
    def _on_download_finished(self, reply: QNetworkReply, metadata: ModlistMetadata, callback, size: str = "small"):
        """Handle download completion"""
        from PySide6.QtWidgets import QApplication
        
        cache_key = f"{metadata.machineURL}_{size}"
        self.downloading.discard(cache_key)
        
        if reply.error() == QNetworkReply.NoError:
            image_data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(image_data) and not pixmap.isNull():
                # Store in memory cache immediately
                self.pixmap_cache[cache_key] = pixmap
                
                # Defer disk save to avoid blocking UI - queue it for later
                cached_path = self.gallery_service.get_image_cache_path(metadata, size)
                self.save_queue.append((pixmap, cached_path))
                self._start_save_timer()
                
                # Call callback with pixmap (update UI immediately)
                if callback:
                    callback(pixmap)
                
                # Process events to keep UI responsive
                QApplication.processEvents()
        
        reply.deleteLater()
        
        # Process next in queue (with small delay to yield to UI)
        QTimer.singleShot(50, self._process_queue)
    
    def _start_save_timer(self):
        """Start timer for deferred disk saves if not already running"""
        if self._save_timer is None:
            self._save_timer = QTimer()
            self._save_timer.timeout.connect(self._save_next_image)
            self._save_timer.setSingleShot(False)
            self._save_timer.start(200)  # Save one image every 200ms
    
    def _save_next_image(self):
        """Save next image from queue to disk (non-blocking)"""
        if self.save_queue:
            pixmap, cached_path = self.save_queue.popleft()
            try:
                cached_path.parent.mkdir(parents=True, exist_ok=True)
                pixmap.save(str(cached_path), "WEBP")
            except Exception:
                pass  # Save failed - not critical, image is in memory cache
        
        # Stop timer if queue is empty
        if not self.save_queue and self._save_timer:
            self._save_timer.stop()
            self._save_timer = None


class ModlistCard(QFrame):
    """Visual card representing a single modlist"""
    clicked = Signal(ModlistMetadata)

    def __init__(self, metadata: ModlistMetadata, image_manager: ImageManager, is_steamdeck: bool = False):
        super().__init__()
        self.metadata = metadata
        self.image_manager = image_manager
        self.is_steamdeck = is_steamdeck
        self._setup_ui()

    def _setup_ui(self):
        """Set up the card UI"""
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setCursor(Qt.PointingHandCursor)
        
        # Steam Deck-specific sizing (1280x800 screen)
        if self.is_steamdeck:
            self.setFixedSize(250, 270)  # Smaller cards for Steam Deck
            image_width, image_height = 230, 130  # Smaller images, maintaining 16:9 ratio
        else:
            self.setFixedSize(300, 320)  # Standard size
            image_width, image_height = 280, 158  # Standard image size
        
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)  # Reduced vertical margins
        layout.setSpacing(6)  # Reduced spacing between elements

        # Image (widescreen aspect ratio like Wabbajack)
        self.image_label = QLabel()
        self.image_label.setFixedSize(image_width, image_height)  # 16:9 aspect ratio
        self.image_label.setStyleSheet("background: #333; border-radius: 4px;")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setScaledContents(True)  # Use Qt's automatic scaling - this works best
        self.image_label.setText("")
        layout.addWidget(self.image_label)

        # Title row with badges (Official, NSFW, UNAVAILABLE)
        title_row = QHBoxLayout()
        title_row.setSpacing(4)

        title = QLabel(self.metadata.title)
        title.setWordWrap(True)
        title.setFont(QFont("Sans", 12, QFont.Bold))
        title.setStyleSheet(f"color: {JACKIFY_COLOR_BLUE};")
        title.setMaximumHeight(40)  # Reduced from 50 to 40
        title_row.addWidget(title, stretch=1)

        # Store reference to unavailable badge for dynamic updates
        self.unavailable_badge = None
        if not self.metadata.is_available():
            self.unavailable_badge = QLabel("UNAVAILABLE")
            self.unavailable_badge.setStyleSheet("background: #666; color: white; padding: 2px 6px; font-size: 9px; border-radius: 3px;")
            self.unavailable_badge.setFixedHeight(20)
            title_row.addWidget(self.unavailable_badge, alignment=Qt.AlignTop | Qt.AlignRight)

        if self.metadata.official:
            official_badge = QLabel("OFFICIAL")
            official_badge.setStyleSheet("background: #2a5; color: white; padding: 2px 6px; font-size: 9px; border-radius: 3px;")
            official_badge.setFixedHeight(20)
            title_row.addWidget(official_badge, alignment=Qt.AlignTop | Qt.AlignRight)

        if self.metadata.nsfw:
            nsfw_badge = QLabel("NSFW")
            nsfw_badge.setStyleSheet("background: #d44; color: white; padding: 2px 6px; font-size: 9px; border-radius: 3px;")
            nsfw_badge.setFixedHeight(20)
            title_row.addWidget(nsfw_badge, alignment=Qt.AlignTop | Qt.AlignRight)

        layout.addLayout(title_row)

        # Author
        author = QLabel(f"by {self.metadata.author}")
        author.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(author)

        # Game
        game = QLabel(self.metadata.gameHumanFriendly)
        game.setStyleSheet("color: #ccc; font-size: 10px;")
        layout.addWidget(game)

        # Sizes (Download, Install, Total)
        if self.metadata.sizes:
            size_info = QLabel(
                f"Download: {self.metadata.sizes.downloadSizeFormatted} | "
                f"Install: {self.metadata.sizes.installSizeFormatted} | "
                f"Total: {self.metadata.sizes.totalSizeFormatted}"
            )
            size_info.setStyleSheet("color: #999; font-size: 10px;")
            size_info.setWordWrap(True)  # Allow wrapping if text is too long
            layout.addWidget(size_info)

        # Removed addStretch() to eliminate wasted space
        self.setLayout(layout)

        # Load image
        self._load_image()

    def _create_placeholder(self):
        """Create a placeholder pixmap for cards without images"""
        # Create placeholder matching the image label size (Steam Deck or standard)
        image_size = self.image_label.size()
        placeholder = QPixmap(image_size)
        placeholder.fill(QColor("#333"))
        
        # Draw a simple icon/text on the placeholder
        painter = QPainter(placeholder)
        painter.setPen(QColor("#666"))
        painter.setFont(QFont("Sans", 10))
        painter.drawText(placeholder.rect(), Qt.AlignCenter, "No Image")
        painter.end()
        
        # Show placeholder immediately
        self.image_label.setPixmap(placeholder)

    def _load_image(self):
        """Load image using centralized image manager - use large images and scale down for quality"""
        # Get large image for card - scale down for better quality than small images
        pixmap = self.image_manager.get_image(self.metadata, self._on_image_loaded, size="large")
        
        if pixmap and not pixmap.isNull():
            # Image was in cache - display immediately (should be instant)
            self._display_image(pixmap)
        else:
            # Image needs to be downloaded - show placeholder
            self._create_placeholder()
    
    def _on_image_loaded(self, pixmap: QPixmap):
        """Callback when image is loaded from network"""
        if pixmap and not pixmap.isNull():
            self._display_image(pixmap)
    
    def _display_image(self, pixmap: QPixmap):
        """Display image - use best method based on aspect ratio"""
        if pixmap.isNull():
            return
        
        label_size = self.image_label.size()
        label_aspect = label_size.width() / label_size.height()  # 16:9 = ~1.778
        
        # Calculate image aspect ratio
        image_aspect = pixmap.width() / pixmap.height() if pixmap.height() > 0 else label_aspect
        
        # If aspect ratios are close (within 5%), use Qt's automatic scaling for best quality
        # Otherwise, manually scale with cropping to avoid stretching
        aspect_diff = abs(image_aspect - label_aspect) / label_aspect
        
        if aspect_diff < 0.05:  # Within 5% of 16:9
            # Close to correct aspect - use Qt's automatic scaling (best quality)
            self.image_label.setScaledContents(True)
            self.image_label.setPixmap(pixmap)
        else:
            # Different aspect - manually scale with cropping (no stretching)
            self.image_label.setScaledContents(False)
            scaled_pixmap = pixmap.scaled(
                label_size.width(),
                label_size.height(),
                Qt.KeepAspectRatioByExpanding,  # Crop instead of stretch
                Qt.SmoothTransformation  # High quality
            )
            self.image_label.setPixmap(scaled_pixmap)
    
    def _update_availability_badge(self):
        """Update unavailable badge visibility based on current availability status"""
        is_unavailable = not self.metadata.is_available()
        
        # Find title row layout (it's the 2nd layout item: image at 0, title_row at 1)
        main_layout = self.layout()
        if main_layout and main_layout.count() >= 2:
            title_row = main_layout.itemAt(1).layout()
            if title_row:
                if is_unavailable and self.unavailable_badge is None:
                    # Need to add badge to title row (before Official/NSFW badges)
                    self.unavailable_badge = QLabel("UNAVAILABLE")
                    self.unavailable_badge.setStyleSheet("background: #666; color: white; padding: 2px 6px; font-size: 9px; border-radius: 3px;")
                    self.unavailable_badge.setFixedHeight(20)
                    # Insert after title (index 1) but before other badges
                    # Find first badge position (if any exist)
                    insert_index = 1  # After title widget
                    for i in range(title_row.count()):
                        item = title_row.itemAt(i)
                        if item and item.widget() and isinstance(item.widget(), QLabel):
                            widget_text = item.widget().text()
                            if widget_text in ("OFFICIAL", "NSFW"):
                                insert_index = i
                                break
                    title_row.insertWidget(insert_index, self.unavailable_badge, alignment=Qt.AlignTop | Qt.AlignRight)
                elif not is_unavailable and self.unavailable_badge is not None:
                    # Need to remove badge from title row
                    title_row.removeWidget(self.unavailable_badge)
                    self.unavailable_badge.setParent(None)
                    self.unavailable_badge = None

    def mousePressEvent(self, event):
        """Handle click on card"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.metadata)
        super().mousePressEvent(event)


class ModlistDetailDialog(QDialog):
    """Detailed view of a modlist with install option"""
    install_requested = Signal(ModlistMetadata)

    def __init__(self, metadata: ModlistMetadata, image_manager: ImageManager, parent=None):
        super().__init__(parent)
        self.metadata = metadata
        self.image_manager = image_manager
        self.setWindowTitle(metadata.title)
        set_responsive_minimum(self, min_width=900, min_height=640)
        self._apply_initial_size()
        self._setup_ui()

    def _apply_initial_size(self):
        """Ensure dialog size fits current screen."""
        _, _, screen_width, screen_height = get_screen_geometry(self)
        width = 1000
        height = 760
        if screen_width:
            width = min(width, max(880, screen_width - 40))
        if screen_height:
            height = min(height, max(640, screen_height - 40))
        self.resize(width, height)

    def _setup_ui(self):
        """Set up detail dialog UI with modern layout matching Wabbajack style"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        # --- Banner area with full-width text overlay ---
        # Container so we can place a semi-opaque text panel over the banner image
        banner_container = QFrame()
        banner_container.setFrameShape(QFrame.NoFrame)
        banner_container.setStyleSheet("background: #000; border: none;")
        banner_layout = QVBoxLayout()
        banner_layout.setContentsMargins(0, 0, 0, 0)
        banner_layout.setSpacing(0)
        banner_container.setLayout(banner_layout)

        # Banner image at top with 16:9 aspect ratio (like Wabbajack)
        self.banner_label = QLabel()
        # Height will be calculated based on width to maintain 16:9 ratio
        self.banner_label.setMinimumHeight(200)
        self.banner_label.setStyleSheet("background: #1a1a1a; border: none;")
        self.banner_label.setAlignment(Qt.AlignCenter)
        self.banner_label.setText("Loading image...")
        banner_layout.addWidget(self.banner_label)

        # Full-width transparent container with opaque card inside (only as wide as text)
        overlay_container = QWidget()
        overlay_container.setStyleSheet("background: transparent;")
        overlay_layout = QHBoxLayout()
        overlay_layout.setContentsMargins(24, 0, 24, 24)
        overlay_layout.setSpacing(0)
        overlay_container.setLayout(overlay_layout)
        
        # Opaque text card - only as wide as content needs (where red lines are)
        self.banner_text_panel = QFrame()
        self.banner_text_panel.setFrameShape(QFrame.StyledPanel)
        # Opaque background, rounded corners, sized to content only
        self.banner_text_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 180);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
            }
        """)
        self.banner_text_panel.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        banner_text_layout = QVBoxLayout()
        banner_text_layout.setContentsMargins(20, 12, 20, 14)
        banner_text_layout.setSpacing(6)
        self.banner_text_panel.setLayout(banner_text_layout)
        
        # Add card to container (left-aligned, rest stays transparent)
        overlay_layout.addWidget(self.banner_text_panel, alignment=Qt.AlignBottom | Qt.AlignLeft)
        overlay_layout.addStretch()  # Push card left, rest transparent

        # Title only (badges moved to tags section below)
        title = QLabel(self.metadata.title)
        title.setFont(QFont("Sans", 24, QFont.Bold))
        title.setStyleSheet(f"color: {JACKIFY_COLOR_BLUE};")
        title.setWordWrap(True)
        banner_text_layout.addWidget(title)

        # Only sizes in overlay (minimal info on image)
        if self.metadata.sizes:
            sizes_text = (
                f"<span style='color: #aaa;'>Download:</span> {self.metadata.sizes.downloadSizeFormatted} • "
                f"<span style='color: #aaa;'>Install:</span> {self.metadata.sizes.installSizeFormatted} • "
                f"<span style='color: #aaa;'>Total:</span> {self.metadata.sizes.totalSizeFormatted}"
            )
            sizes_label = QLabel(sizes_text)
            sizes_label.setStyleSheet("color: #fff; font-size: 13px;")
            banner_text_layout.addWidget(sizes_label)

        # Add full-width transparent container at bottom of banner
        banner_layout.addWidget(overlay_container, alignment=Qt.AlignBottom)
        main_layout.addWidget(banner_container)

        # Content area with padding (tags + description + bottom bar)
        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)
        content_widget.setLayout(content_layout)

        # Metadata line (version, author, game) - moved below image
        metadata_line_parts = []
        if self.metadata.version:
            metadata_line_parts.append(f"<span style='color: #aaa;'>version</span> {self.metadata.version}")
        metadata_line_parts.append(f"<span style='color: #aaa;'>by</span> {self.metadata.author}")
        metadata_line_parts.append(f"<span style='color: #aaa;'>•</span> {self.metadata.gameHumanFriendly}")
        
        if self.metadata.maintainers and len(self.metadata.maintainers) > 0:
            maintainers_text = ", ".join(self.metadata.maintainers)
            if maintainers_text != self.metadata.author:  # Only show if different from author
                metadata_line_parts.append(f"<span style='color: #aaa;'>•</span> Maintained by {maintainers_text}")
        
        metadata_line = QLabel(" ".join(metadata_line_parts))
        metadata_line.setStyleSheet("color: #fff; font-size: 14px;")
        metadata_line.setWordWrap(True)
        content_layout.addWidget(metadata_line)

        # Tags row (includes status badges moved from overlay)
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(6)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add status badges first (UNAVAILABLE, Unofficial)
        if not self.metadata.is_available():
            unavailable_badge = QLabel("UNAVAILABLE")
            unavailable_badge.setStyleSheet("background: #666; color: white; padding: 6px 12px; font-size: 11px; border-radius: 4px;")
            tags_layout.addWidget(unavailable_badge)
        
        if not self.metadata.official:
            unofficial_badge = QLabel("Unofficial")
            unofficial_badge.setStyleSheet("background: #666; color: white; padding: 6px 12px; font-size: 11px; border-radius: 4px;")
            tags_layout.addWidget(unofficial_badge)
        
        # Add regular tags
        tags_to_render = getattr(self.metadata, 'normalized_tags_display', self.metadata.tags or [])
        if tags_to_render:
            for tag in tags_to_render:
                tag_badge = QLabel(tag)
                # Match Wabbajack tag styling
                if tag.lower() == "nsfw":
                    tag_badge.setStyleSheet("background: #d44; color: white; padding: 6px 12px; font-size: 11px; border-radius: 4px;")
                elif tag.lower() == "official" or tag.lower() == "featured":
                    tag_badge.setStyleSheet("background: #2a5; color: white; padding: 6px 12px; font-size: 11px; border-radius: 4px;")
                else:
                    tag_badge.setStyleSheet("background: #3a3a3a; color: #ccc; padding: 6px 12px; font-size: 11px; border-radius: 4px;")
                tags_layout.addWidget(tag_badge)
        
        tags_layout.addStretch()
        content_layout.addLayout(tags_layout)

        # Description section
        desc_label = QLabel("<b style='color: #aaa; font-size: 14px;'>Description:</b>")
        content_layout.addWidget(desc_label)

        # Use QTextEdit with explicit line counting to force scrollbar
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setPlainText(self.metadata.description or "No description provided.")
        # Compact description area; scroll when content is long
        self.desc_text.setFixedHeight(120)
        self.desc_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.desc_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.desc_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.desc_text.setStyleSheet("""
            QTextEdit {
                background: #2a2a2a;
                color: #fff;
                border: none;
                border-radius: 6px;
                padding: 12px;
            }
        """)

        content_layout.addWidget(self.desc_text)

        main_layout.addWidget(content_widget)

        # Bottom bar with Links (left) and Action buttons (right)
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(24, 16, 24, 24)
        bottom_bar.setSpacing(12)
        
        # Links section on the left
        links_layout = QHBoxLayout()
        links_layout.setSpacing(10)
        
        if self.metadata.links and (self.metadata.links.discordURL or self.metadata.links.websiteURL or self.metadata.links.readme):
            links_label = QLabel("<b style='color: #aaa; font-size: 14px;'>Links:</b>")
            links_layout.addWidget(links_label)
            
            if self.metadata.links.discordURL:
                discord_btn = QPushButton("Discord")
                discord_btn.setStyleSheet("""
                    QPushButton {
                        background: #5865F2;
                        color: white;
                        padding: 8px 16px;
                        border: none;
                        border-radius: 6px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: #4752C4;
                    }
                    QPushButton:pressed {
                        background: #3C45A5;
                    }
                """)
                discord_btn.clicked.connect(lambda: self._open_url(self.metadata.links.discordURL))
                links_layout.addWidget(discord_btn)
            
            if self.metadata.links.websiteURL:
                website_btn = QPushButton("Website")
                website_btn.setStyleSheet("""
                    QPushButton {
                        background: #3a3a3a;
                        color: white;
                        padding: 8px 16px;
                        border: none;
                        border-radius: 6px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: #4a4a4a;
                    }
                    QPushButton:pressed {
                        background: #2a2a2a;
                    }
                """)
                website_btn.clicked.connect(lambda: self._open_url(self.metadata.links.websiteURL))
                links_layout.addWidget(website_btn)
            
            if self.metadata.links.readme:
                readme_btn = QPushButton("Readme")
                readme_btn.setStyleSheet("""
                    QPushButton {
                        background: #3a3a3a;
                        color: white;
                        padding: 8px 16px;
                        border: none;
                        border-radius: 6px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: #4a4a4a;
                    }
                    QPushButton:pressed {
                        background: #2a2a2a;
                    }
                """)
                readme_url = self._convert_raw_github_url(self.metadata.links.readme)
                readme_btn.clicked.connect(lambda: self._open_url(readme_url))
                links_layout.addWidget(readme_btn)
        
        bottom_bar.addLayout(links_layout)
        bottom_bar.addStretch()

        # Action buttons on the right

        cancel_btn = QPushButton("Close")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
            QPushButton:pressed {
                background: #2a2a2a;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        bottom_bar.addWidget(cancel_btn)

        install_btn = QPushButton("Install Modlist")
        install_btn.setDefault(True)
        if not self.metadata.is_available():
            install_btn.setEnabled(False)
            install_btn.setToolTip("This modlist is currently unavailable")
            install_btn.setStyleSheet("""
                QPushButton {
                    background: #555;
                    color: #999;
                    padding: 8px 16px;
                    border: none;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                }
            """)
        else:
            install_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {JACKIFY_COLOR_BLUE};
                    color: white;
                    padding: 8px 16px;
                    border: none;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: #4a9eff;
                }}
                QPushButton:pressed {{
                    background: #3a8eef;
                }}
            """)
        install_btn.clicked.connect(self._on_install_clicked)
        bottom_bar.addWidget(install_btn)

        main_layout.addLayout(bottom_bar)
        self.setLayout(main_layout)
        
        # Load banner image
        self._load_banner_image()

    def _load_banner_image(self):
        """Load large banner image for detail view"""
        if not self.metadata.images or not self.metadata.images.large:
            self.banner_label.setText("No image available")
            self.banner_label.setStyleSheet("background: #1a1a1a; color: #666; border: none;")
            return
        
        # Try to get large image from cache or download (for detail view banner)
        pixmap = self.image_manager.get_image(self.metadata, self._on_banner_loaded, size="large")
        
        if pixmap and not pixmap.isNull():
            # Image was in cache - display immediately
            self._display_banner(pixmap)
        else:
            # Show placeholder while downloading
            placeholder = QPixmap(self.banner_label.size())
            placeholder.fill(QColor("#1a1a1a"))
            painter = QPainter(placeholder)
            painter.setPen(QColor("#666"))
            painter.setFont(QFont("Sans", 12))
            painter.drawText(placeholder.rect(), Qt.AlignCenter, "Loading image...")
            painter.end()
            self.banner_label.setPixmap(placeholder)
    
    def _on_banner_loaded(self, pixmap: QPixmap):
        """Callback when banner image is loaded"""
        if pixmap and not pixmap.isNull():
            self._display_banner(pixmap)
    
    def resizeEvent(self, event):
        """Handle dialog resize to maintain 16:9 aspect ratio for banner"""
        super().resizeEvent(event)
        # Update banner height to maintain 16:9 aspect ratio
        if hasattr(self, 'banner_label'):
            width = self.width()
            height = int(width / 16 * 9)  # 16:9 aspect ratio
            self.banner_label.setFixedHeight(height)
            # Redisplay image if we have one
            if hasattr(self, '_current_banner_pixmap'):
                self._display_banner(self._current_banner_pixmap)
    
    def _display_banner(self, pixmap: QPixmap):
        """Display banner image with proper 16:9 aspect ratio (like Wabbajack)"""
        # Store pixmap for resize events
        self._current_banner_pixmap = pixmap
        
        # Calculate 16:9 aspect ratio height
        width = self.width() if self.width() > 0 else 1000
        target_height = int(width / 16 * 9)
        self.banner_label.setFixedHeight(target_height)
        
        # Scale image to fill width while maintaining aspect ratio (UniformToFill behavior)
        # This crops if needed but doesn't stretch
        scaled_pixmap = pixmap.scaled(
            width,
            target_height,
            Qt.KeepAspectRatioByExpanding,  # Fill the area, cropping if needed
            Qt.SmoothTransformation
        )
        self.banner_label.setPixmap(scaled_pixmap)
        self.banner_label.setText("")

    def _convert_raw_github_url(self, url: str) -> str:
        """Convert raw GitHub URLs to rendered blob URLs for better user experience"""
        if not url:
            return url

        if "raw.githubusercontent.com" in url:
            url = url.replace("raw.githubusercontent.com", "github.com")
            url = url.replace("/master/", "/blob/master/")
            url = url.replace("/main/", "/blob/main/")

        return url

    def _on_install_clicked(self):
        """Handle install button click"""
        self.install_requested.emit(self.metadata)
        self.accept()

    def _open_url(self, url: str):
        """Open URL with clean environment to avoid AppImage library conflicts."""
        import subprocess
        import os

        env = os.environ.copy()

        # Remove AppImage-specific environment variables
        appimage_vars = [
            'LD_LIBRARY_PATH',
            'PYTHONPATH',
            'PYTHONHOME',
            'QT_PLUGIN_PATH',
            'QML2_IMPORT_PATH',
        ]

        if 'APPIMAGE' in env or 'APPDIR' in env:
            for var in appimage_vars:
                if var in env:
                    del env[var]

        subprocess.Popen(
            ['xdg-open', url],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )


class ModlistGalleryDialog(QDialog):
    """Enhanced modlist gallery dialog with visual browsing"""
    modlist_selected = Signal(ModlistMetadata)

    def __init__(self, game_filter: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Modlist")
        self.setModal(True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#111111"))
        self.setPalette(palette)
        
        # Detect Steam Deck
        from jackify.backend.services.platform_detection_service import PlatformDetectionService
        platform_service = PlatformDetectionService.get_instance()
        self.is_steamdeck = platform_service.is_steamdeck
        
        # Responsive sizing for different screen sizes (especially Steam Deck 1280x800)
        min_height = 650 if self.is_steamdeck else 700
        set_responsive_minimum(self, min_width=1100 if self.is_steamdeck else 1200, min_height=min_height)
        self._apply_initial_size()

        self.gallery_service = ModlistGalleryService()
        self.image_manager = ImageManager(self.gallery_service)
        self.all_modlists: List[ModlistMetadata] = []
        self.filtered_modlists: List[ModlistMetadata] = []
        self.game_filter = game_filter
        self.selected_metadata: Optional[ModlistMetadata] = None
        self.all_cards: Dict[str, ModlistCard] = {}  # Dict keyed by machineURL for quick lookup
        self._validation_update_timer = None  # Timer for background validation updates

        self._setup_ui()
        # Disable filter controls during initial load to prevent race conditions
        self._set_filter_controls_enabled(False)
        # Lazy load - fetch modlists when dialog is shown

    def _apply_initial_size(self):
        """Ensure dialog fits on screen while maximizing usable space."""
        _, _, screen_width, screen_height = get_screen_geometry(self)
        width = 1400
        height = 800
        
        if self.is_steamdeck or (screen_width and screen_width <= 1280):
            width = min(width, 1200)
            height = min(height, 750)
        
        if screen_width:
            width = min(width, max(1000, screen_width - 40))
        if screen_height:
            height = min(height, max(640, screen_height - 40))
        
        self.resize(width, height)

    def showEvent(self, event):
        """Fetch modlists when dialog is first shown"""
        super().showEvent(event)
        if not self.all_modlists:
            # Start loading in background thread for instant dialog appearance
            self._load_modlists_async()

    def _setup_ui(self):
        """Set up the gallery UI"""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)  # Reduced from 20 to 16
        main_layout.setSpacing(12)

        # Left sidebar (filters)
        filter_panel = self._create_filter_panel()
        main_layout.addWidget(filter_panel)

        # Right content area (modlist grid)
        self.content_area = self._create_content_area()
        main_layout.addWidget(self.content_area, stretch=1)

        self.setLayout(main_layout)

    def _create_filter_panel(self) -> QWidget:
        """Create filter sidebar"""
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setFixedWidth(280)  # Slightly wider for better readability

        layout = QVBoxLayout()
        layout.setSpacing(6)  # Reduced from 12 to 6 for tighter spacing

        # Title
        title = QLabel("<b>Filters</b>")
        title.setStyleSheet(f"font-size: 14px; color: {JACKIFY_COLOR_BLUE};")
        layout.addWidget(title)

        # Search box (label removed - placeholder text is clear enough)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search modlists...")
        self.search_box.setStyleSheet("QLineEdit { background: #2a2a2a; color: #fff; border: 1px solid #555; padding: 4px; }")
        self.search_box.textChanged.connect(self._apply_filters)
        layout.addWidget(self.search_box)

        # Game filter (label removed - combo box is self-explanatory)
        self.game_combo = QComboBox()
        self.game_combo.addItem("All Games", None)
        self.game_combo.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.game_combo)

        # Status filters
        self.show_official_only = QCheckBox("Show Official Only")
        self.show_official_only.stateChanged.connect(self._apply_filters)
        layout.addWidget(self.show_official_only)

        self.show_nsfw = QCheckBox("Show NSFW")
        self.show_nsfw.stateChanged.connect(self._on_nsfw_toggled)
        layout.addWidget(self.show_nsfw)

        self.hide_unavailable = QCheckBox("Hide Unavailable")
        self.hide_unavailable.setChecked(True)
        self.hide_unavailable.stateChanged.connect(self._apply_filters)
        layout.addWidget(self.hide_unavailable)

        # Tag filter
        tags_label = QLabel("Tags:")
        layout.addWidget(tags_label)
        
        self.tags_list = QListWidget()
        self.tags_list.setSelectionMode(QListWidget.MultiSelection)
        self.tags_list.setMaximumHeight(150)
        self.tags_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # Remove horizontal scrollbar
        self.tags_list.setStyleSheet("QListWidget { background: #2a2a2a; color: #fff; border: 1px solid #555; }")
        self.tags_list.itemSelectionChanged.connect(self._apply_filters)
        layout.addWidget(self.tags_list)

        # Add spacing between Tags and Mods sections
        layout.addSpacing(8)

        # Mod filter - TEMPORARILY DISABLED (not working correctly in v0.2.0.8)
        # TODO: Re-enable once mod search index issue is resolved
        # mods_label = QLabel("Mods:")
        # layout.addWidget(mods_label)
        #
        # self.mod_search = QLineEdit()
        # self.mod_search.setPlaceholderText("Search mods...")
        # self.mod_search.setStyleSheet("QLineEdit { background: #2a2a2a; color: #fff; border: 1px solid #555; padding: 4px; }")
        # self.mod_search.textChanged.connect(self._filter_mods_list)
        # # Prevent Enter from triggering default button (which would close dialog)
        # self.mod_search.returnPressed.connect(lambda: self.mod_search.clearFocus())
        # layout.addWidget(self.mod_search)
        #
        # self.mods_list = QListWidget()
        # self.mods_list.setSelectionMode(QListWidget.MultiSelection)
        # self.mods_list.setMaximumHeight(150)
        # self.mods_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # Remove horizontal scrollbar
        # self.mods_list.setStyleSheet("QListWidget { background: #2a2a2a; color: #fff; border: 1px solid #555; }")
        # self.mods_list.itemSelectionChanged.connect(self._apply_filters)
        # layout.addWidget(self.mods_list)
        #
        # self.all_mods_list = []  # Store all mods for filtering

        layout.addStretch()

        # Cancel button (not default to prevent Enter from closing)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setDefault(False)
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        panel.setLayout(layout)
        return panel

    def _create_content_area(self) -> QWidget:
        """Create modlist grid content area"""
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Status label (subtle, top-right) - hidden during initial loading (popup shows instead)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        layout.addWidget(self.status_label)

        # Scroll area for modlist cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Grid container for cards
        self.grid_widget = QWidget()
        # Don't use WA_StaticContents - we need resize events to recalculate columns
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(8)  # Reduced from 12 to 8 for tighter card spacing
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_widget.setLayout(self.grid_layout)

        self.scroll_area.setWidget(self.grid_widget)
        layout.addWidget(self.scroll_area)

        container.setLayout(layout)
        return container

    def _load_modlists_async(self):
        """Load modlists in background thread for instant dialog appearance"""
        from PySide6.QtCore import QThread, Signal
        from PySide6.QtGui import QFont

        # Hide status label during loading (popup dialog will show instead)
        self.status_label.setVisible(False)
        
        # Show loading overlay directly in content area (simpler than separate dialog)
        self._loading_overlay = QWidget(self.content_area)
        self._loading_overlay.setStyleSheet("""
            QWidget {
                background-color: rgba(35, 35, 35, 240);
                border-radius: 8px;
            }
        """)
        overlay_layout = QVBoxLayout()
        overlay_layout.setContentsMargins(30, 20, 30, 20)
        overlay_layout.setSpacing(12)
        
        self._loading_label = QLabel("Loading modlists")
        self._loading_label.setAlignment(Qt.AlignCenter)
        # Set fixed width to prevent text shifting when dots animate
        # Width accommodates "Loading modlists..." (longest version)
        self._loading_label.setFixedWidth(220)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self._loading_label.setFont(font)
        self._loading_label.setStyleSheet(f"color: {JACKIFY_COLOR_BLUE}; font-size: 14px; font-weight: bold;")
        overlay_layout.addWidget(self._loading_label)
        
        self._loading_overlay.setLayout(overlay_layout)
        self._loading_overlay.setFixedSize(300, 120)
        
        # Animate dots in loading message
        self._loading_dot_count = 0
        self._loading_dot_timer = QTimer()
        self._loading_dot_timer.timeout.connect(self._animate_loading_dots)
        self._loading_dot_timer.start(500)  # Update every 500ms
        
        # Position overlay in center of content area
        def position_overlay():
            if hasattr(self, 'content_area') and self.content_area.isVisible():
                content_width = self.content_area.width()
                content_height = self.content_area.height()
                x = (content_width - 300) // 2
                y = (content_height - 120) // 2
                self._loading_overlay.move(x, y)
                self._loading_overlay.show()
                self._loading_overlay.raise_()
        
        # Delay slightly to ensure content_area is laid out
        QTimer.singleShot(50, position_overlay)

        class ModlistLoaderThread(QThread):
            """Background thread to load modlist metadata"""
            finished = Signal(object, object)  # metadata_response, error_message

            def __init__(self, gallery_service):
                super().__init__()
                self.gallery_service = gallery_service

            def run(self):
                try:
                    import time
                    start_time = time.time()

                    # Fetch metadata (CPU-intensive work happens here in background)
                    # Skip search index initially for faster loading - can be loaded later if user searches
                    metadata_response = self.gallery_service.fetch_modlist_metadata(
                        include_validation=False,
                        include_search_index=False,  # Skip for faster initial load
                        sort_by="title"
                    )

                    elapsed = time.time() - start_time
                    import logging
                    logger = logging.getLogger(__name__)
                    if elapsed < 0.5:
                        logger.debug(f"Gallery metadata loaded from cache in {elapsed:.2f}s")
                    else:
                        logger.info(f"Gallery metadata fetched from engine in {elapsed:.2f}s")

                    self.finished.emit(metadata_response, None)
                except Exception as e:
                    self.finished.emit(None, str(e))

        # Create and start background thread
        self._loader_thread = ModlistLoaderThread(self.gallery_service)
        self._loader_thread.finished.connect(self._on_modlists_loaded)
        self._loader_thread.start()

    def _animate_loading_dots(self):
        """Animate dots in loading message"""
        if hasattr(self, '_loading_label') and self._loading_label:
            self._loading_dot_count = (self._loading_dot_count + 1) % 4
            dots = "." * self._loading_dot_count
            # Pad with spaces to keep text width constant (prevents shifting)
            padding = " " * (3 - self._loading_dot_count)
            self._loading_label.setText(f"Loading modlists{dots}{padding}")
    
    def _on_modlists_loaded(self, metadata_response, error_message):
        """Handle modlist metadata loaded in background thread (runs in GUI thread)"""
        import random
        from PySide6.QtGui import QFont

        # Stop animation timer and close loading overlay
        if hasattr(self, '_loading_dot_timer') and self._loading_dot_timer:
            self._loading_dot_timer.stop()
            self._loading_dot_timer = None
        
        if hasattr(self, '_loading_overlay') and self._loading_overlay:
            self._loading_overlay.hide()
            self._loading_overlay.deleteLater()
            self._loading_overlay = None
        
        self.status_label.setVisible(True)

        if error_message:
            self.status_label.setText(f"Error loading modlists: {error_message}")
            return

        if not metadata_response:
            self.status_label.setText("Failed to load modlists")
            return

        try:
            # Get all modlists
            all_modlists = metadata_response.modlists

            # RANDOMIZE the order each time gallery opens (like Wabbajack)
            random.shuffle(all_modlists)

            self.all_modlists = all_modlists

            # Precompute normalized tags for display/filtering
            for modlist in self.all_modlists:
                normalized_display = self.gallery_service.normalize_tags_for_display(getattr(modlist, 'tags', []))
                modlist.normalized_tags_display = normalized_display
                modlist.normalized_tags_keys = [tag.lower() for tag in normalized_display]

            # Temporarily disconnect to prevent triggering during setup
            self.game_combo.currentIndexChanged.disconnect(self._apply_filters)

            # Populate game filter
            games = sorted(set(m.gameHumanFriendly for m in self.all_modlists))
            for game in games:
                self.game_combo.addItem(game, game)

            # If dialog was opened with a game filter, pre-select it
            if self.game_filter:
                index = self.game_combo.findData(self.game_filter)
                if index >= 0:
                    self.game_combo.setCurrentIndex(index)

            # Populate tag filter (mod filter temporarily disabled)
            self._populate_tag_filter()
            # self._populate_mod_filter()  # TEMPORARILY DISABLED

            # Create cards immediately (will show placeholders for images not in cache)
            self._create_all_cards()

            # Preload cached images in background (non-blocking)
            self.status_label.setText("Loading images...")
            QTimer.singleShot(0, self._preload_cached_images_async)

            # Reconnect filter handler
            self.game_combo.currentIndexChanged.connect(self._apply_filters)

            # Enable filter controls now that data is loaded
            self._set_filter_controls_enabled(True)

            # Apply filters (will show all modlists for selected game initially)
            self._apply_filters()

            # Start background validation update (non-blocking)
            self._start_validation_update()

        except Exception as e:
            self.status_label.setText(f"Error processing modlists: {str(e)}")

    def _load_modlists(self):
        """DEPRECATED: Synchronous loading - replaced by _load_modlists_async()"""
        from PySide6.QtWidgets import QApplication

        self.status_label.setText("Loading modlists...")
        QApplication.processEvents()  # Update UI immediately

        # Fetch metadata (will use cache if valid)
        # Skip validation initially for faster loading - can be added later if needed
        try:
            metadata_response = self.gallery_service.fetch_modlist_metadata(
                include_validation=False,  # Skip validation for faster initial load
                include_search_index=True,  # Include mod search index for mod filtering
                sort_by="title"
            )

            if metadata_response:
                # Get all modlists
                all_modlists = metadata_response.modlists
                
                # RANDOMIZE the order each time gallery opens (like Wabbajack)
                # This prevents authors from gaming the system with alphabetical ordering
                random.shuffle(all_modlists)
                
                self.all_modlists = all_modlists

                # Precompute normalized tags for display/filtering (matches upstream Wabbajack)
                for modlist in self.all_modlists:
                    normalized_display = self.gallery_service.normalize_tags_for_display(getattr(modlist, 'tags', []))
                    modlist.normalized_tags_display = normalized_display
                    modlist.normalized_tags_keys = [tag.lower() for tag in normalized_display]

                # Temporarily disconnect to prevent triggering during setup
                self.game_combo.currentIndexChanged.disconnect(self._apply_filters)

                # Populate game filter
                games = sorted(set(m.gameHumanFriendly for m in self.all_modlists))
                for game in games:
                    self.game_combo.addItem(game, game)

                # If dialog was opened with a game filter, pre-select it
                if self.game_filter:
                    index = self.game_combo.findData(self.game_filter)
                    if index >= 0:
                        self.game_combo.setCurrentIndex(index)

                # Populate tag filter (mod filter temporarily disabled)
                self._populate_tag_filter()
                # self._populate_mod_filter()  # TEMPORARILY DISABLED

                # Create cards immediately (will show placeholders for images not in cache)
                self._create_all_cards()
                
                # Preload cached images in background (non-blocking)
                # Images will appear as they're loaded
                self.status_label.setText("Loading images...")
                QTimer.singleShot(0, self._preload_cached_images_async)

                # Reconnect filter handler
                self.game_combo.currentIndexChanged.connect(self._apply_filters)

                # Apply filters (will show all modlists for selected game initially)
                self._apply_filters()
                
                # Start background validation update (non-blocking)
                self._start_validation_update()
            else:
                self.status_label.setText("Failed to load modlists")
        except Exception as e:
            self.status_label.setText(f"Error loading modlists: {str(e)}")

    def _preload_cached_images_async(self):
        """Preload cached images asynchronously - images appear as they load"""
        from PySide6.QtWidgets import QApplication
        
        preloaded = 0
        total = len(self.all_modlists)
        
        for idx, modlist in enumerate(self.all_modlists):
            cache_key = modlist.machineURL
            
            # Skip if already in cache
            if cache_key in self.image_manager.pixmap_cache:
                continue
            
            # Preload large images for cards (scale down for better quality)
            cached_path = self.gallery_service.get_cached_image_path(modlist, "large")
            if cached_path and cached_path.exists():
                try:
                    pixmap = QPixmap(str(cached_path))
                    if not pixmap.isNull():
                        cache_key_large = f"{cache_key}_large"
                        self.image_manager.pixmap_cache[cache_key_large] = pixmap
                        preloaded += 1
                        
                        # Update card immediately if it exists
                        card = self.all_cards.get(cache_key)
                        if card:
                            card._display_image(pixmap)
                except Exception:
                    pass
            
            # Process events every 10 images to keep UI responsive
            if idx % 10 == 0 and idx > 0:
                QApplication.processEvents()
        
        # Update status (subtle, user-friendly)
        modlist_count = len(self.filtered_modlists)
        if modlist_count == 1:
            self.status_label.setText("1 modlist")
        else:
            self.status_label.setText(f"{modlist_count} modlists")

    def _populate_tag_filter(self):
        """Populate tag filter with normalized tags (like Wabbajack)"""
        normalized_tags = set()
        for modlist in self.all_modlists:
            display_tags = getattr(modlist, 'normalized_tags_display', None)
            if display_tags is None:
                display_tags = self.gallery_service.normalize_tags_for_display(getattr(modlist, 'tags', []))
                modlist.normalized_tags_display = display_tags
                modlist.normalized_tags_keys = [tag.lower() for tag in display_tags]
            normalized_tags.update(display_tags)
        
        # Add special tags (like Wabbajack)
        normalized_tags.add("NSFW")
        normalized_tags.add("Featured")  # Official
        normalized_tags.add("Unavailable")
        
        self.tags_list.clear()
        for tag in sorted(normalized_tags):
            self.tags_list.addItem(tag)
    
    def _get_normalized_tag_display(self, modlist: ModlistMetadata) -> List[str]:
        """Return (and cache) normalized tags for display for a modlist."""
        display_tags = getattr(modlist, 'normalized_tags_display', None)
        if display_tags is None:
            display_tags = self.gallery_service.normalize_tags_for_display(getattr(modlist, 'tags', []))
            modlist.normalized_tags_display = display_tags
            modlist.normalized_tags_keys = [tag.lower() for tag in display_tags]
        return display_tags

    def _get_normalized_tag_keys(self, modlist: ModlistMetadata) -> List[str]:
        """Return (and cache) lowercase normalized tags for filtering."""
        keys = getattr(modlist, 'normalized_tags_keys', None)
        if keys is None:
            display_tags = self._get_normalized_tag_display(modlist)
            keys = [tag.lower() for tag in display_tags]
            modlist.normalized_tags_keys = keys
        return keys

    def _tag_in_modlist(self, modlist: ModlistMetadata, normalized_tag_key: str) -> bool:
        """Check if a normalized (lowercase) tag is present on a modlist."""
        keys = self._get_normalized_tag_keys(modlist)
        return any(key == normalized_tag_key for key in keys)
    
    def _populate_mod_filter(self):
        """Populate mod filter with all available mods from search index"""
        # TEMPORARILY DISABLED - mod filter feature removed in v0.2.0.8
        return

        # all_mods = set()
        # # Track which mods come from NSFW modlists only
        # mods_from_nsfw_only = set()
        # mods_from_sfw = set()
        # modlists_with_mods = 0
        #
        # for modlist in self.all_modlists:
        #     if hasattr(modlist, 'mods') and modlist.mods:
        #         modlists_with_mods += 1
        #         for mod in modlist.mods:
        #             all_mods.add(mod)
        #             if modlist.nsfw:
        #                 mods_from_nsfw_only.add(mod)
        #             else:
        #                 mods_from_sfw.add(mod)
        #
        # # Mods that are ONLY in NSFW modlists (not in any SFW modlists)
        # self.nsfw_only_mods = mods_from_nsfw_only - mods_from_sfw
        #
        # self.all_mods_list = sorted(all_mods)
        #
        # self._filter_mods_list("")  # Populate with all mods initially
    
    def _filter_mods_list(self, search_text: str = ""):
        """Filter the mods list based on search text and NSFW checkbox"""
        # TEMPORARILY DISABLED - mod filter feature removed in v0.2.0.8
        return

        # Get search text from the widget if not provided
        # if not search_text and hasattr(self, 'mod_search'):
        #     search_text = self.mod_search.text()
        #
        # self.mods_list.clear()
        # search_lower = search_text.lower().strip()
        #
        # # Start with all mods or filtered by search
        # if search_lower:
        #     filtered_mods = [m for m in self.all_mods_list if search_lower in m.lower()]
        # else:
        #     filtered_mods = self.all_mods_list
        #
        # # Filter out NSFW-only mods if NSFW checkbox is not checked
        # if not self.show_nsfw.isChecked():
        #     filtered_mods = [m for m in filtered_mods if m not in getattr(self, 'nsfw_only_mods', set())]
        #
        # # Limit to first 500 results for performance
        # for mod in filtered_mods[:500]:
        #     self.mods_list.addItem(mod)
        #
        # if len(filtered_mods) > 500:
        #     self.mods_list.addItem(f"... and {len(filtered_mods) - 500} more (refine search)")
    
    def _on_nsfw_toggled(self, checked: bool):
        """Handle NSFW checkbox toggle - refresh mod list and apply filters"""
        # self._filter_mods_list()  # TEMPORARILY DISABLED - Refresh mod list based on NSFW state
        self._apply_filters()  # Apply all filters
    
    def _set_filter_controls_enabled(self, enabled: bool):
        """Enable or disable all filter controls"""
        self.search_box.setEnabled(enabled)
        self.game_combo.setEnabled(enabled)
        self.show_official_only.setEnabled(enabled)
        self.show_nsfw.setEnabled(enabled)
        self.hide_unavailable.setEnabled(enabled)
        self.tags_list.setEnabled(enabled)
        # self.mod_search.setEnabled(enabled)  # TEMPORARILY DISABLED
        # self.mods_list.setEnabled(enabled)  # TEMPORARILY DISABLED
    
    def _apply_filters(self):
        """Apply current filters to modlist display"""
        # CRITICAL: Guard against race condition - don't filter if modlists aren't loaded yet
        if not self.all_modlists:
            return
        
        filtered = self.all_modlists

        # Search filter
        search_text = self.search_box.text().strip()
        if search_text:
            filtered = [m for m in filtered if self._matches_search(m, search_text)]

        # Game filter
        game = self.game_combo.currentData()
        if game:
            filtered = [m for m in filtered if m.gameHumanFriendly == game]

        # Status filters
        if self.show_official_only.isChecked():
            filtered = [m for m in filtered if m.official]

        if not self.show_nsfw.isChecked():
            filtered = [m for m in filtered if not m.nsfw]

        if self.hide_unavailable.isChecked():
            filtered = [m for m in filtered if m.is_available()]

        # Tag filter - modlist must have ALL selected tags (normalized like Wabbajack)
        selected_tags = [item.text() for item in self.tags_list.selectedItems()]
        if selected_tags:
            special_selected = {tag for tag in selected_tags if tag in ("NSFW", "Featured", "Unavailable")}
            normalized_selected = [
                self.gallery_service.normalize_tag_value(tag).lower()
                for tag in selected_tags
                if tag not in special_selected
            ]

            if "NSFW" in special_selected:
                filtered = [m for m in filtered if m.nsfw]
            if "Featured" in special_selected:
                filtered = [m for m in filtered if m.official]
            if "Unavailable" in special_selected:
                filtered = [m for m in filtered if not m.is_available()]

            if normalized_selected:
                filtered = [
                    m for m in filtered
                    if all(
                        self._tag_in_modlist(m, normalized_tag)
                        for normalized_tag in normalized_selected
                    )
                ]

        # Mod filter - TEMPORARILY DISABLED (not working correctly in v0.2.0.8)
        # selected_mods = [item.text() for item in self.mods_list.selectedItems()]
        # if selected_mods:
        #     filtered = [m for m in filtered if m.mods and all(mod in m.mods for mod in selected_mods)]

        self.filtered_modlists = filtered
        self._update_grid()

    def _matches_search(self, modlist: ModlistMetadata, query: str) -> bool:
        """Check if modlist matches search query"""
        query_lower = query.lower()
        return (
            query_lower in modlist.title.lower() or
            query_lower in modlist.description.lower() or
            query_lower in modlist.author.lower()
        )

    def _create_all_cards(self):
        """Create cards for all modlists and store in dict"""
        # Clear existing cards
        self.all_cards.clear()
        
        # Disable updates during card creation to prevent individual renders
        self.grid_widget.setUpdatesEnabled(False)
        self.setUpdatesEnabled(False)
        
        try:
            # Create all cards - images should be in memory cache from preload
            # so _load_image() will find them instantly
            for modlist in self.all_modlists:
                card = ModlistCard(modlist, self.image_manager, is_steamdeck=self.is_steamdeck)
                card.clicked.connect(self._on_modlist_clicked)
                self.all_cards[modlist.machineURL] = card
        finally:
            # Re-enable updates - single render for all cards
            self.setUpdatesEnabled(True)
            self.grid_widget.setUpdatesEnabled(True)
            self.grid_widget.update()

    def _update_grid(self):
        """Update grid by removing all cards and re-adding only visible ones"""
        # CRITICAL: Guard against race condition - don't update if cards aren't ready yet
        if not self.all_cards:
            return
        
        # Disable updates during grid update
        self.grid_widget.setUpdatesEnabled(False)
        
        try:
            # Remove all cards from layout
            # CRITICAL FIX: Properly remove all widgets to prevent overlapping
            # Iterate backwards to avoid index shifting issues
            for i in range(self.grid_layout.count() - 1, -1, -1):
                item = self.grid_layout.takeAt(i)
                widget = item.widget() if item else None
                if widget:
                    # Hide widget during removal to prevent visual artifacts
                    widget.hide()
                del item
            
            # Force layout update to ensure all widgets are removed
            self.grid_layout.update()

            # Calculate number of columns based on available width
            # Get the scroll area width (accounting for filter panel ~280px + margins)
            scroll_area = self.grid_widget.parent()
            if scroll_area and hasattr(scroll_area, 'viewport'):
                available_width = scroll_area.viewport().width()
            else:
                # Fallback: estimate based on dialog width minus filter panel
                available_width = self.width() - 280 - 32  # Filter panel + margins
            
            if available_width <= 0:
                # Fallback if width not yet calculated
                available_width = 900 if not self.is_steamdeck else 700
            
            # Card width + spacing between cards
            if self.is_steamdeck:
                card_width = 250
            else:
                card_width = 300
            
            card_spacing = 8
            # Calculate how many columns fit
            columns = max(1, int((available_width + card_spacing) / (card_width + card_spacing)))
            
            # Limit to reasonable max (4 columns on large screens, 3 on Steam Deck)
            if not self.is_steamdeck:
                columns = min(columns, 4)
            else:
                columns = min(columns, 3)

            # Preserve randomized order (already shuffled in _load_modlists)
            # Add visible cards to grid in order
            for idx, modlist in enumerate(self.filtered_modlists):
                row = idx // columns
                col = idx % columns
                
                card = self.all_cards.get(modlist.machineURL)
                if card:
                    # Safety check: ensure widget is not already in the layout
                    # (shouldn't happen after proper removal above, but defensive programming)
                    already_in_layout = False
                    for i in range(self.grid_layout.count()):
                        item = self.grid_layout.itemAt(i)
                        if item and item.widget() == card:
                            # Widget is already in layout - this shouldn't happen, but handle it
                            already_in_layout = True
                            self.grid_layout.removeWidget(card)
                            break
                    
                    # Ensure widget is visible and add to grid
                    if not already_in_layout or card.isHidden():
                        card.show()
                    self.grid_layout.addWidget(card, row, col)
            
            # Set column stretch - don't stretch card columns, but add a spacer column
            for col in range(columns):
                self.grid_layout.setColumnStretch(col, 0)  # Cards are fixed width
            # Add a stretch column after cards to fill remaining space (centers the grid)
            if columns < 4:
                self.grid_layout.setColumnStretch(columns, 1)
        finally:
            # Re-enable updates
            self.grid_widget.setUpdatesEnabled(True)
            self.grid_widget.update()

        # Update status
        self.status_label.setText(f"Showing {len(self.filtered_modlists)} modlists")

    def resizeEvent(self, event):
        """Handle dialog resize to recalculate grid columns"""
        super().resizeEvent(event)
        # Recalculate columns when dialog is resized
        if hasattr(self, 'filtered_modlists') and self.filtered_modlists:
            self._update_grid()

    def _on_modlist_clicked(self, metadata: ModlistMetadata):
        """Handle modlist card click - show detail dialog"""
        dialog = ModlistDetailDialog(metadata, self.image_manager, self)
        dialog.install_requested.connect(self._on_install_requested)
        dialog.exec()

    def _on_install_requested(self, metadata: ModlistMetadata):
        """Handle install request from detail dialog"""
        self.selected_metadata = metadata
        self.modlist_selected.emit(metadata)
        self.accept()

    def _refresh_metadata(self):
        """Force refresh metadata from jackify-engine"""
        self.status_label.setText("Refreshing metadata...")
        self.gallery_service.clear_cache()
        self._load_modlists()
    
    def _start_validation_update(self):
        """Start background validation update to get availability status"""
        # Update validation in background thread to avoid blocking UI
        class ValidationUpdateThread(QThread):
            finished_signal = Signal(object)  # Emits updated metadata response
            
            def __init__(self, gallery_service):
                super().__init__()
                self.gallery_service = gallery_service
            
            def run(self):
                try:
                    # Fetch with validation (slower, but in background)
                    metadata_response = self.gallery_service.fetch_modlist_metadata(
                        include_validation=True,
                        include_search_index=False,
                        sort_by="title"
                    )
                    self.finished_signal.emit(metadata_response)
                except Exception:
                    self.finished_signal.emit(None)
        
        self._validation_thread = ValidationUpdateThread(self.gallery_service)
        self._validation_thread.finished_signal.connect(self._on_validation_updated)
        self._validation_thread.start()
    
    def _on_validation_updated(self, metadata_response):
        """Update modlists with validation data when background fetch completes"""
        if not metadata_response:
            return
        
        # Create lookup dict for validation data
        validation_map = {}
        for modlist in metadata_response.modlists:
            if modlist.validation:
                validation_map[modlist.machineURL] = modlist.validation
        
        # Update existing modlists with validation data
        updated_count = 0
        for modlist in self.all_modlists:
            if modlist.machineURL in validation_map:
                modlist.validation = validation_map[modlist.machineURL]
                updated_count += 1
                
                # Update card if it exists
                card = self.all_cards.get(modlist.machineURL)
                if card:
                    # Update unavailable badge visibility
                    card._update_availability_badge()
        
        # Re-apply filters to update availability filtering
        if updated_count > 0:
            self._apply_filters()
