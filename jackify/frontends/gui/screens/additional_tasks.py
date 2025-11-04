"""
Additional Tasks & Tools Screen

Simple screen for TTW automation only.
Follows the same pattern as ModlistTasksScreen.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from jackify.backend.models.configuration import SystemInfo
from ..shared_theme import JACKIFY_COLOR_BLUE

logger = logging.getLogger(__name__)


class AdditionalTasksScreen(QWidget):
    """Simple Additional Tasks screen for TTW only"""

    def __init__(self, stacked_widget=None, main_menu_index=0, system_info: Optional[SystemInfo] = None):
        super().__init__()
        self.stacked_widget = stacked_widget
        self.main_menu_index = main_menu_index
        self.system_info = system_info or SystemInfo(is_steamdeck=False)
        
        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface following ModlistTasksScreen pattern"""
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        
        # Header section
        self._setup_header(layout)
        
        # Menu buttons section
        self._setup_menu_buttons(layout)
        
        # Bottom spacer
        layout.addStretch()
        self.setLayout(layout)

    def _setup_header(self, layout):
        """Set up the header section"""
        header_layout = QVBoxLayout()
        header_layout.setSpacing(0)
        
        # Title
        title = QLabel("<b>Additional Tasks & Tools</b>")
        title.setStyleSheet(f"font-size: 24px; color: {JACKIFY_COLOR_BLUE};")
        title.setAlignment(Qt.AlignHCenter)
        header_layout.addWidget(title)

        # Add a spacer to match main menu vertical spacing
        header_layout.addSpacing(16)
        
        # Description  
        desc = QLabel(
            "TTW automation and additional tools.<br>&nbsp;"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #ccc;")
        desc.setAlignment(Qt.AlignHCenter)
        header_layout.addWidget(desc)
        
        header_layout.addSpacing(24)
        
        # Separator (shorter like main menu)
        sep = QLabel()
        sep.setFixedHeight(2)
        sep.setFixedWidth(400)  # Match button width
        sep.setStyleSheet("background: #fff;")
        header_layout.addWidget(sep, alignment=Qt.AlignHCenter)
        
        header_layout.addSpacing(16)
        layout.addLayout(header_layout)
    
    def _setup_menu_buttons(self, layout):
        """Set up the menu buttons section"""
        # Menu options - ONLY TTW and placeholder
        MENU_ITEMS = [
            ("Install TTW", "ttw_install", "Install Tale of Two Wastelands using Hoolamike automation"),
            ("Coming Soon...", "coming_soon", "Additional tools will be added in future updates"),
            ("Return to Main Menu", "return_main_menu", "Go back to the main menu"),
        ]
        
        # Create grid layout for buttons (mirror ModlistTasksScreen pattern)
        button_grid = QGridLayout()
        button_grid.setSpacing(16)
        button_grid.setAlignment(Qt.AlignHCenter)

        button_width = 400
        button_height = 50

        for i, (label, action_id, description) in enumerate(MENU_ITEMS):
            # Create button
            btn = QPushButton(label)
            btn.setFixedSize(button_width, button_height)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #4a5568;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background-color: #5a6578;
                }}
                QPushButton:pressed {{
                    background-color: {JACKIFY_COLOR_BLUE};
                }}
            """)
            btn.clicked.connect(lambda checked, a=action_id: self._handle_button_click(a))

            # Description label
            desc_label = QLabel(description)
            desc_label.setAlignment(Qt.AlignHCenter)
            desc_label.setStyleSheet("color: #999; font-size: 12px;")
            desc_label.setWordWrap(True)
            desc_label.setFixedWidth(button_width)

            # Add to grid (button row, then description row)
            button_grid.addWidget(btn, i * 2, 0, Qt.AlignHCenter)
            button_grid.addWidget(desc_label, i * 2 + 1, 0, Qt.AlignHCenter)

        layout.addLayout(button_grid)

    # Removed _create_menu_button; using same pattern as ModlistTasksScreen

    def _handle_button_click(self, action_id):
        """Handle button clicks"""
        if action_id == "ttw_install":
            self._show_ttw_info()
        elif action_id == "coming_soon":
            self._show_coming_soon_info()
        elif action_id == "return_main_menu":
            self._return_to_main_menu()

    def _show_ttw_info(self):
        """Navigate to TTW installation screen"""
        if self.stacked_widget:
            # Navigate to TTW installation screen (index 5)
            self.stacked_widget.setCurrentIndex(5)

    def _show_coming_soon_info(self):
        """Show coming soon info"""
        from ..services.message_service import MessageService
        MessageService.information(
            self,
            "Coming Soon",
            "Additional tools and features will be added in future updates.\n\n"
            "Check back later for more functionality!"
        )

    def _return_to_main_menu(self):
        """Return to main menu"""
        if self.stacked_widget:
            self.stacked_widget.setCurrentIndex(self.main_menu_index)