"""
Progress Indicator Widget

Enhanced status banner widget that displays overall installation progress.
R&D NOTE: This is experimental code for investigation purposes.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from jackify.shared.progress_models import InstallationProgress
from ..shared_theme import JACKIFY_COLOR_BLUE


class OverallProgressIndicator(QWidget):
    """
    Enhanced progress indicator widget showing:
    - Phase name
    - Step progress [12/14]
    - Data progress (1.1GB/56.3GB)
    - Overall percentage
    - Optional progress bar
    """
    
    def __init__(self, parent=None, show_progress_bar=True):
        """
        Initialize progress indicator.
        
        Args:
            parent: Parent widget
            show_progress_bar: If True, show visual progress bar in addition to text
        """
        super().__init__(parent)
        self.show_progress_bar = show_progress_bar
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Status text label (similar to TTW status banner)
        self.status_label = QLabel("Ready to install")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"""
            background-color: #2a2a2a;
            color: {JACKIFY_COLOR_BLUE};
            padding: 6px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 13px;
        """)
        self.status_label.setMaximumHeight(34)
        self.status_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
        # Progress bar (optional, shown below or integrated)
        if self.show_progress_bar:
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            # Use white text with shadow/outline effect for readability on both dark and blue backgrounds
            self.progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid #444;
                    border-radius: 4px;
                    text-align: center;
                    background-color: #1a1a1a;
                    color: #fff;
                    font-weight: bold;
                    height: 20px;
                }}
                QProgressBar::chunk {{
                    background-color: {JACKIFY_COLOR_BLUE};
                    border-radius: 3px;
                }}
            """)
            self.progress_bar.setMaximumHeight(20)
            self.progress_bar.setVisible(True)
        
        # Layout: text on left, progress bar on right (or stacked)
        if self.show_progress_bar:
            # Horizontal layout: status text takes available space, progress bar fixed width
            layout.addWidget(self.status_label, 1)
            layout.addWidget(self.progress_bar, 0)  # Fixed width
            self.progress_bar.setFixedWidth(100)  # Fixed width for progress bar
        else:
            # Just the status label, full width
            layout.addWidget(self.status_label, 1)
        
        # Constrain widget height to prevent unwanted vertical expansion
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(34)  # Match status label height
    
    def update_progress(self, progress: InstallationProgress):
        """
        Update the progress indicator with new progress state.
        
        Args:
            progress: InstallationProgress object with current state
        """
        # Update status text
        display_text = progress.display_text
        if not display_text or display_text == "Processing...":
            display_text = progress.phase_name or progress.phase.value.title() or "Processing..."
        
        self.status_label.setText(display_text)
        
        # Update progress bar if enabled
        if self.show_progress_bar and hasattr(self, 'progress_bar'):
            # Calculate progress - prioritize data progress, then step progress, then overall_percent
            display_percent = 0.0
            
            # Check if we're in BSA building phase (detected by phase label)
            from jackify.shared.progress_models import InstallationPhase
            is_bsa_building = progress.get_phase_label() == "Building BSAs"
            
            # For install/extract/BSA building phases, prefer step-based progress (more accurate)
            if progress.phase in (InstallationPhase.INSTALL, InstallationPhase.EXTRACT) or is_bsa_building:
                if progress.phase_max_steps > 0:
                    display_percent = (progress.phase_step / progress.phase_max_steps) * 100.0
                elif progress.data_total > 0 and progress.data_processed > 0:
                    display_percent = (progress.data_processed / progress.data_total) * 100.0
                else:
                    # If no step/data info, use overall_percent but only if it's reasonable
                    # Don't carry over 100% from previous phase
                    if progress.overall_percent > 0 and progress.overall_percent < 100.0:
                        display_percent = progress.overall_percent
                    else:
                        display_percent = 0.0  # Reset if we don't have valid progress
            else:
                # For other phases, prefer data progress, then overall_percent, then step progress
                if progress.data_total > 0 and progress.data_processed > 0:
                    display_percent = (progress.data_processed / progress.data_total) * 100.0
                elif progress.overall_percent > 0:
                    display_percent = progress.overall_percent
                elif progress.phase_max_steps > 0:
                    display_percent = (progress.phase_step / progress.phase_max_steps) * 100.0
            
            self.progress_bar.setValue(int(display_percent))
            
            # Update tooltip with detailed information
            tooltip_parts = []
            if progress.phase_name:
                tooltip_parts.append(f"Phase: {progress.phase_name}")
            if progress.phase_progress_text:
                tooltip_parts.append(f"Step: {progress.phase_progress_text}")
            if progress.data_progress_text:
                tooltip_parts.append(f"Data: {progress.data_progress_text}")
            if progress.overall_percent > 0:
                tooltip_parts.append(f"Overall: {progress.overall_percent:.1f}%")
            
            if tooltip_parts:
                self.progress_bar.setToolTip("\n".join(tooltip_parts))
                self.status_label.setToolTip("\n".join(tooltip_parts))
    
    def set_status(self, text: str, percent: int = None):
        """
        Set status text directly without full progress update.

        Args:
            text: Status text to display
            percent: Optional progress percentage (0-100)
        """
        self.status_label.setText(text)
        if percent is not None and self.show_progress_bar and hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(int(percent))

    def reset(self):
        """Reset the progress indicator to initial state."""
        self.status_label.setText("Ready to install")
        if self.show_progress_bar and hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(0)
            self.progress_bar.setToolTip("")
            self.status_label.setToolTip("")

