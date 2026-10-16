from PySide6.QtWidgets import QLabel

from musicorg.plugins.hooks import SidebarPageSpec


class Plugin:
    def initialize(self, context):
        self.context = context

    def start(self):
        return

    def stop(self):
        return

    def dispose(self):
        return

    def register_sidebar_pages(self):
        return [
            SidebarPageSpec(
                page_id="hello",
                title="Hello",
                icon="H",
                widget_factory=lambda parent: QLabel("Hello from docs example", parent),
            )
        ]
