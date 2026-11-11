"""Best-effort process-tree RSS sampling; not GPU allocation accounting."""

import subprocess
import threading
from urllib.parse import urlsplit


class ResourceMonitor:
    def __init__(self, spec, client):
        self.stop_event = threading.Event()
        self.peak_kib = None
        self.error = None
        try:
            if hasattr(client, 'process'):
                self.pid = client.process.pid
            else:
                port = urlsplit(spec['base_url']).port or 80
                p = subprocess.run(['lsof', '-tiTCP:' + str(port), '-sTCP:LISTEN'], capture_output=True, text=True, timeout=3)
                self.pid = int(p.stdout.splitlines()[0])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            self.pid = None
            self.error = 'process identity unavailable'
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while not self.stop_event.is_set() and self.pid:
            try:
                p = subprocess.run(['ps', '-axo', 'pid=,ppid=,rss='], capture_output=True, text=True, timeout=2)
                if p.returncode:
                    raise OSError('process metrics unavailable')
                rows = [tuple(map(int, line.split())) for line in p.stdout.splitlines()]
                descendants = {self.pid}
                for _ in range(len(rows)):
                    expanded = descendants | {pid for pid, parent, _ in rows if parent in descendants}
                    if expanded == descendants:
                        break
                    descendants = expanded
                rss = sum(size for pid, _, size in rows if pid in descendants)
                self.peak_kib = max(self.peak_kib or 0, rss)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                self.error = 'RSS sampling unavailable'
                break
            self.stop_event.wait(1)

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=3)
        return {'process_tree_peak_rss_kib': self.peak_kib, 'error': self.error,
                'scope': 'generation phase only; shared service tree when HTTP; external engines may be outside this tree; RSS may double-count mappings and omits GPU allocations; not whole-engine peak memory'}
