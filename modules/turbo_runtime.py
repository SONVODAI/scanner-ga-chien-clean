from modules.cache_manager import (
    exists,
    load_dataframe,
    save_dataframe,
    clear_cache,
)


class TurboRuntime:

    def __init__(self):
        self.scan_df = None
        self.market = None
        self.last_scan_time = None

    def has(self, name: str):
        return exists(name)

    def load(self, name: str):
        return load_dataframe(name)

    def save(self, name: str, df):
        save_dataframe(name, df)

    def clear(self):
        self.scan_df = None
        self.market = None
        self.last_scan_time = None
        clear_cache()


turbo = TurboRuntime()
