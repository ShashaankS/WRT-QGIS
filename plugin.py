import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon

class WRTPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "Weather Routing Tool", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("Weather Routing Tool", self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removePluginMenu("Weather Routing Tool", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self):
        QMessageBox.information(
            self.iface.mainWindow(),
            "Weather Routing Tool",
            "Plugin is loaded.",
        )
