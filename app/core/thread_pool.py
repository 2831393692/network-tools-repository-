from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import QThread, Signal, QObject

class Worker(QObject):
    finished = Signal(object)
    error = Signal(Exception)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(e)

class TaskThread(QThread):
    result_ready = Signal(object)
    task_error = Signal(Exception)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.result_ready.emit(result)
        except Exception as e:
            self.task_error.emit(e)

class ThreadPool:
    _instance = None
    
    def __new__(cls, max_workers=20):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.executor = ThreadPoolExecutor(max_workers=max_workers)
        return cls._instance
    
    def submit(self, func, *args, **kwargs):
        return self.executor.submit(func, *args, **kwargs)
    
    def map(self, func, iterable, timeout=None):
        return self.executor.map(func, iterable, timeout=timeout)
    
    def run_in_thread(self, func, callback=None, error_callback=None, *args, **kwargs):
        thread = TaskThread(func, *args, **kwargs)
        if callback:
            thread.result_ready.connect(callback)
        if error_callback:
            thread.task_error.connect(error_callback)
        thread.start()
        return thread
    
    def shutdown(self, wait=True):
        self.executor.shutdown(wait=wait)
    
    def get_executor(self):
        return self.executor