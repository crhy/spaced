from PyQt5.QtWidgets import QApplication, QTextEdit
from PyQt5.QtCore import Qt
class Probe(QTextEdit):
    def wheelEvent(self, event):
        with open('/tmp/qt-wheel-events.log', 'a') as log:
            log.write(f'wheel angle={event.angleDelta().y()} pixel={event.pixelDelta().y()} mods={int(event.modifiers())}\n')
        super().wheelEvent(event)
app = QApplication([])
w = Probe()
w.setWindowTitle('Release Qt wheel probe')
w.setPlainText('\n'.join(f'Line {i}' for i in range(500)))
w.resize(700,500)
w.show()
app.exec_()
