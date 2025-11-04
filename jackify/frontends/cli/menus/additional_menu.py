"""
Additional Tasks Menu Handler for Jackify CLI Frontend
Extracted from src.modules.menu_handler.MenuHandler.show_additional_tasks_menu()
"""

import time

from jackify.shared.colors import (
    COLOR_SELECTION, COLOR_RESET, COLOR_ACTION, COLOR_PROMPT, COLOR_INFO, COLOR_DISABLED, COLOR_WARNING
)
from jackify.shared.ui_utils import print_jackify_banner, print_section_header, clear_screen

class AdditionalMenuHandler:
    """
    Handles the Additional Tasks menu (MO2, NXM Handling & Recovery)
    Extracted from legacy MenuHandler class
    """
    
    def __init__(self):
        self.logger = None  # Will be set by CLI when needed
    
    def _clear_screen(self):
        """Clear the terminal screen with AppImage compatibility"""
        clear_screen()
    
    def show_additional_tasks_menu(self, cli_instance):
        """Show the Additional Tasks & Tools submenu"""
        while True:
            self._clear_screen()
            print_jackify_banner()
            print_section_header("Additional Tasks & Tools")
            print(f"{COLOR_INFO}Additional Tasks & Tools, such as TTW Installation{COLOR_RESET}\n")

            print(f"{COLOR_SELECTION}1.{COLOR_RESET} Tale of Two Wastelands (TTW) Installation")
            print(f"   {COLOR_ACTION}→ Install TTW using Hoolamike native automation{COLOR_RESET}")
            print(f"{COLOR_SELECTION}2.{COLOR_RESET} Coming Soon...")
            print(f"{COLOR_SELECTION}0.{COLOR_RESET} Return to Main Menu")
            selection = input(f"\n{COLOR_PROMPT}Enter your selection (0-2): {COLOR_RESET}").strip()
            
            if selection.lower() == 'q':  # Allow 'q' to re-display menu
                continue
            if selection == "1":
                self._execute_hoolamike_ttw_install(cli_instance)
            elif selection == "2":
                print(f"\n{COLOR_INFO}More features coming soon!{COLOR_RESET}")
                input("\nPress Enter to return to menu...")
            elif selection == "0":
                break
            else:
                print("Invalid selection. Please try again.")
                time.sleep(1)

    def _execute_legacy_install_mo2(self, cli_instance):
        """LEGACY BRIDGE: Execute MO2 installation"""
        # LEGACY BRIDGE: Use legacy imports until backend migration complete
        if hasattr(cli_instance, 'menu') and hasattr(cli_instance.menu, 'mo2_handler'):
            cli_instance.menu.mo2_handler.install_mo2()
        else:
            print(f"{COLOR_INFO}MO2 handler not available - this will be implemented in Phase 2.3{COLOR_RESET}")
            input("\nPress Enter to continue...")

    def _execute_legacy_recovery_menu(self, cli_instance):
        """LEGACY BRIDGE: Execute recovery menu"""
        # This will be handled by the RecoveryMenuHandler
        from .recovery_menu import RecoveryMenuHandler
        
        recovery_handler = RecoveryMenuHandler()
        recovery_handler.logger = self.logger
        recovery_handler.show_recovery_menu(cli_instance)

    def _execute_hoolamike_ttw_install(self, cli_instance):
        """Execute TTW installation using Hoolamike handler"""
        from ....backend.handlers.hoolamike_handler import HoolamikeHandler
        from ....backend.models.configuration import SystemInfo
        from ....shared.colors import COLOR_ERROR

        system_info = SystemInfo(is_steamdeck=cli_instance.system_info.is_steamdeck)
        hoolamike_handler = HoolamikeHandler(
            steamdeck=system_info.is_steamdeck,
            verbose=cli_instance.verbose,
            filesystem_handler=cli_instance.filesystem_handler,
            config_handler=cli_instance.config_handler,
            menu_handler=cli_instance.menu_handler
        )

        # First check if Hoolamike is installed
        if not hoolamike_handler.hoolamike_installed:
            print(f"\n{COLOR_WARNING}Hoolamike is not installed. Installing Hoolamike first...{COLOR_RESET}")
            if not hoolamike_handler.install_update_hoolamike():
                print(f"{COLOR_ERROR}Failed to install Hoolamike. Cannot proceed with TTW installation.{COLOR_RESET}")
                input("Press Enter to return to menu...")
                return

        # Run TTW installation workflow
        print(f"\n{COLOR_INFO}Starting TTW installation workflow...{COLOR_RESET}")
        result = hoolamike_handler.install_ttw()
        if result is None:
            print(f"\n{COLOR_WARNING}TTW installation returned without result.{COLOR_RESET}")
            input("Press Enter to return to menu...")

    def _execute_hoolamike_modlist_install(self, cli_instance):
        """Execute modlist installation using Hoolamike handler"""
        from ....backend.handlers.hoolamike_handler import HoolamikeHandler
        from ....backend.models.configuration import SystemInfo

        system_info = SystemInfo(is_steamdeck=cli_instance.system_info.is_steamdeck)
        hoolamike_handler = HoolamikeHandler(
            steamdeck=system_info.is_steamdeck,
            verbose=cli_instance.verbose,
            filesystem_handler=cli_instance.filesystem_handler,
            config_handler=cli_instance.config_handler,
            menu_handler=cli_instance.menu_handler
        )

        # First check if Hoolamike is installed
        if not hoolamike_handler.hoolamike_installed:
            print(f"\n{COLOR_WARNING}Hoolamike is not installed. Installing Hoolamike first...{COLOR_RESET}")
            if not hoolamike_handler.install_update_hoolamike():
                print(f"{COLOR_ERROR}Failed to install Hoolamike. Cannot proceed with modlist installation.{COLOR_RESET}")
                input("Press Enter to return to menu...")
                return

        # Run modlist installation
        hoolamike_handler.install_modlist() 