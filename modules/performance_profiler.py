import time


class Profiler:
    def __init__(self):
        self.data = {}

    def start(self, name):
        self.data[name] = time.perf_counter()

    def stop(self, name):
        if name in self.data:
            self.data[name] = time.perf_counter() - self.data[name]

    def report(self):
        return self.data


profiler = Profiler()
