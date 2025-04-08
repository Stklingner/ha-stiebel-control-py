"""
Application Lifecycle Management for Stiebel Control.

This module provides a structured approach to managing the application's
lifecycle, including initialization, startup, shutdown, and resource cleanup.
"""

import logging
import signal
import sys
from typing import List, Optional, Callable, Any, Dict

# Configure logger
logger = logging.getLogger(__name__)


class LifecycleManager:
    """
    Manages the application lifecycle.
    
    Provides hooks for initialization, startup, shutdown, and cleanup,
    as well as signal handling for graceful shutdown.
    """
    
    def __init__(self, application_name: str = "Application"):
        """
        Initialize the lifecycle manager.
        
        Args:
            application_name: Name of the application for logging purposes
        """
        self.application_name = application_name
        self.components = []
        self.is_running = False
        self.init_callbacks = []
        self.start_callbacks = []
        self.stop_callbacks = []
        self.cleanup_callbacks = []
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"{self.application_name} lifecycle manager initialized")
    
    def register_component(self, component: Any, 
                          init_method: Optional[Callable] = None,
                          start_method: Optional[Callable] = None,
                          stop_method: Optional[Callable] = None,
                          cleanup_method: Optional[Callable] = None):
        """
        Register a component with the lifecycle manager.
        
        Args:
            component: The component to register
            init_method: Optional method to call during initialization phase
            start_method: Optional method to call during startup phase
            stop_method: Optional method to call during shutdown phase
            cleanup_method: Optional method to call during cleanup phase
        """
        self.components.append(component)
        
        if init_method:
            self.register_init_callback(init_method)
        
        if start_method:
            self.register_start_callback(start_method)
        
        if stop_method:
            self.register_stop_callback(stop_method)
        
        if cleanup_method:
            self.register_cleanup_callback(cleanup_method)
    
    def register_init_callback(self, callback: Callable):
        """Register a callback for the initialization phase."""
        self.init_callbacks.append(callback)
    
    def register_start_callback(self, callback: Callable):
        """Register a callback for the startup phase."""
        self.start_callbacks.append(callback)
    
    def register_stop_callback(self, callback: Callable):
        """Register a callback for the shutdown phase."""
        self.stop_callbacks.append(callback)
    
    def register_cleanup_callback(self, callback: Callable):
        """Register a callback for the cleanup phase."""
        self.cleanup_callbacks.append(callback)
    
    def initialize(self) -> bool:
        """
        Run the initialization phase.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        logger.info(f"Initializing {self.application_name}...")
        try:
            for callback in self.init_callbacks:
                callback()
            logger.info(f"{self.application_name} initialization completed")
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    def start(self) -> bool:
        """
        Run the startup phase.
        
        Returns:
            bool: True if startup was successful, False otherwise
        """
        logger.info(f"Starting {self.application_name}...")
        try:
            for callback in self.start_callbacks:
                callback()
            self.is_running = True
            logger.info(f"{self.application_name} started")
            return True
        except Exception as e:
            logger.error(f"Startup failed: {e}")
            self.cleanup()
            return False
    
    def stop(self) -> bool:
        """
        Run the shutdown phase.
        
        Returns:
            bool: True if shutdown was successful, False otherwise
        """
        if not self.is_running:
            return True
            
        logger.info(f"Stopping {self.application_name}...")
        self.is_running = False
        
        success = True
        for callback in reversed(self.stop_callbacks):
            try:
                callback()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
                success = False
                
        logger.info(f"{self.application_name} stopped")
        return success
    
    def cleanup(self) -> bool:
        """
        Run the cleanup phase.
        
        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        logger.info(f"Cleaning up {self.application_name} resources...")
        
        success = True
        for callback in reversed(self.cleanup_callbacks):
            try:
                callback()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                success = False
                
        logger.info(f"{self.application_name} cleanup completed")
        return success
    
    def shutdown(self) -> bool:
        """
        Run both stop and cleanup phases.
        
        Returns:
            bool: True if both phases were successful, False otherwise
        """
        stop_success = self.stop()
        cleanup_success = self.cleanup()
        return stop_success and cleanup_success
    
    def _signal_handler(self, sig, frame) -> None:
        """
        Handle signals for graceful shutdown.
        
        Args:
            sig: Signal number
            frame: Current stack frame
        """
        logger.info(f"Received signal {sig}, shutting down")
        self.shutdown()
        sys.exit(0)


class ApplicationContext:
    """
    Central context object for the application.
    
    Holds references to all major components and provides
    dependency injection functionality.
    """
    
    def __init__(self):
        """Initialize the application context."""
        self._components = {}
        self.lifecycle_manager = LifecycleManager("Stiebel Control")
    
    def register_component(self, name: str, component: Any,
                          init_method: Optional[Callable] = None,
                          start_method: Optional[Callable] = None,
                          stop_method: Optional[Callable] = None,
                          cleanup_method: Optional[Callable] = None):
        """
        Register a component with the application context.
        
        Args:
            name: Name to use for the component
            component: The component to register
            init_method: Optional method to call during initialization phase
            start_method: Optional method to call during startup phase
            stop_method: Optional method to call during shutdown phase
            cleanup_method: Optional method to call during cleanup phase
        """
        self._components[name] = component
        self.lifecycle_manager.register_component(
            component,
            init_method,
            start_method,
            stop_method,
            cleanup_method
        )
    
    def get_component(self, name: str) -> Any:
        """
        Get a component by name.
        
        Args:
            name: Name of the component to get
            
        Returns:
            The component, or None if not found
        """
        return self._components.get(name)
    
    def initialize(self) -> bool:
        """Initialize all components."""
        return self.lifecycle_manager.initialize()
    
    def start(self) -> bool:
        """Start all components."""
        return self.lifecycle_manager.start()
    
    def stop(self) -> bool:
        """Stop all components."""
        return self.lifecycle_manager.stop()
    
    def cleanup(self) -> bool:
        """Clean up all components."""
        return self.lifecycle_manager.cleanup()
    
    def shutdown(self) -> bool:
        """Shut down the application."""
        return self.lifecycle_manager.shutdown()
