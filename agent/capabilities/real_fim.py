import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import socketio
import asyncio
import os
import platform

# Check if we can import BaseCapability, otherwise standalone for now
try:
    from agent.capabilities.base import BaseCapability
except ImportError:
    class BaseCapability:
        pass

logger = logging.getLogger(__name__)

class FileEventStreamer(FileSystemEventHandler):
    def __init__(self, sio, agent_id):
        self.sio = sio
        self.agent_id = agent_id

    def on_modified(self, event):
        if not event.is_directory:
            self._emit_event("modified", event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._emit_event("created", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._emit_event("deleted", event.src_path)

    def _emit_event(self, type, path):
        print(f"[FIM] File {type}: {path}")
        asyncio.run_coroutine_threadsafe(
            self.sio.emit('security_event', {
                'type': 'fim_alert',
                'severity': 'high',
                'title': f'Critical File {type.title()}',
                'message': f'File {path} was {type}.',
                'agent_id': self.agent_id,
                'source': 'FileWatcher'
            }), self.loop
        )
    
    def set_loop(self, loop):
        self.loop = loop

class RealTimeFIMCapability(BaseCapability):
    """
    Real-time File Integrity Monitoring using Watchdog and WebSocket
    """
    def __init__(self, config=None):
        self.config = config or {}
        self.capability_name = "fim"
        self.observer = None
        self.sio = None
        self.agent_id = self.config.get("agent_id", "unknown-agent")

    def start_watching(self):
        # Initialize WebSocket connection
        self.sio = socketio.AsyncClient()
        
        # Connect to backend
        async def connect_and_stream():
            try:
                await self.sio.connect('http://localhost:5000', auth={'tenant_id': 'platform-admin', 'agent_id': self.agent_id})
                logger.info("Connected to WebSocket for FIM Streaming")
            except Exception as e:
                logger.error(f"Failed to connect WebSocket: {e}")

        # In a real agent, we'd run this loop. 
        # For this implementation, we assume it's integrated into the main asyncio loop
        # or we fire-and-forget for now.
        
        # Determine paths
        paths = ["/etc/passwd", "C:\\Windows\\System32\\drivers\\etc\\hosts"]
        existing_paths = [p for p in paths if os.path.exists(p)]
        
        if not existing_paths:
            logger.warning("No critical files found to watch on this OS.")
            return

        self.observer = Observer()
        handler = FileEventStreamer(self.sio, self.agent_id)
        # We need the loop from sio
        # handler.set_loop(asyncio.get_event_loop()) 
        # This part is tricky without running in the main loop.

        for path in existing_paths:
             dir_path = os.path.dirname(path)
             self.observer.schedule(handler, dir_path, recursive=False)
        
        self.observer.start()
        logger.info(f"Started Real-time FIM on {existing_paths}")

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
        if self.sio:
            asyncio.run(self.sio.disconnect())

