"""
CAD Agent tab — generates build123d STL models from text prompts.
3D preview via QWebEngineView + Three.js (falls back to file info if WebEngine absent).
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Slot, Signal
from PySide6.QtGui import QFont

from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit, StrongBodyLabel,
    CaptionLabel, CardWidget, TextEdit, PushButton
)

from core.agent.cad_agent import CadAgent, OUTPUT_DIR

# Check build123d availability (requires Python <3.13)
try:
    import build123d  # noqa: F401
    _HAS_BUILD123D = True
except ImportError:
    _HAS_BUILD123D = False

# Try to import QWebEngineView — optional, requires Python <3.13 + PySide6-WebEngine
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

# ── Three.js STL viewer HTML ──────────────────────────────────────────────────

_VIEWER_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
  body { margin: 0; background: #0d1117; overflow: hidden; font-family: monospace; }
  #info { position: absolute; top: 8px; left: 8px; color: #58a6ff; font-size: 11px;
          pointer-events: none; }
  #placeholder { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
                 color: #444; font-size: 13px; text-align: center; }
</style>
</head>
<body>
<div id="info"></div>
<div id="placeholder">Generate a model to preview it here</div>
<script type="importmap">
{"imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}}
</script>
<script type="module">
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 10000);
camera.position.set(80, 80, 80);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.2);
sun.position.set(50, 100, 80);
sun.castShadow = true;
scene.add(sun);
const fill = new THREE.DirectionalLight(0x4488ff, 0.3);
fill.position.set(-50, -20, -50);
scene.add(fill);

const grid = new THREE.GridHelper(300, 30, 0x222233, 0x1a1a2e);
scene.add(grid);

let currentMesh = null;

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

window.loadSTLData = function(b64data, filename) {
  if (currentMesh) { scene.remove(currentMesh); currentMesh = null; }
  document.getElementById('placeholder').style.display = 'none';

  const binary = atob(b64data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  const loader = new STLLoader();
  const geometry = loader.parse(bytes.buffer);
  geometry.computeBoundingBox();
  geometry.center();

  const mat = new THREE.MeshStandardMaterial({
    color: 0x00b4d8, roughness: 0.25, metalness: 0.15
  });
  currentMesh = new THREE.Mesh(geometry, mat);
  currentMesh.castShadow = true;
  currentMesh.receiveShadow = true;
  scene.add(currentMesh);

  // Fit camera to model
  const box = new THREE.Box3().setFromObject(currentMesh);
  const size = box.getSize(new THREE.Vector3()).length();
  const center = box.getCenter(new THREE.Vector3());
  camera.position.set(center.x + size, center.y + size * 0.7, center.z + size);
  controls.target.copy(center);
  controls.update();

  const verts = geometry.attributes.position.count;
  const tris = Math.round(verts / 3);
  const sz = box.getSize(new THREE.Vector3());
  document.getElementById('info').textContent =
    (filename || '') + '  |  ' + tris + ' triangles  |  ' +
    sz.x.toFixed(1) + ' × ' + sz.y.toFixed(1) + ' × ' + sz.z.toFixed(1) + ' mm';
};
</script>
</body></html>"""


class _WorkerThread(QThread):
    """Runs CadAgent.generate / iterate in a background thread."""

    def __init__(self, agent: CadAgent, prompt: str, current_code: str = "", parent=None):
        super().__init__(parent)
        self._agent = agent
        self._prompt = prompt
        self._current_code = current_code

    def run(self):
        if self._current_code:
            self._agent.iterate(self._prompt, self._current_code)
        else:
            self._agent.generate(self._prompt)


class CadTab(QWidget):
    """Interactive CAD generation tab with 3D STL preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cadInterface")
        self._agent = None
        self._worker = None
        self._current_code = ""
        self._current_stl = ""
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(StrongBodyLabel("CAD Agent", self))

        # Input row
        row = QHBoxLayout()
        self.prompt_input = LineEdit(self)
        self.prompt_input.setPlaceholderText(
            "Describe the 3D model… e.g. 'a 30mm cube with a 10mm hole through the center'"
        )
        self.prompt_input.returnPressed.connect(self._on_generate)
        row.addWidget(self.prompt_input)

        self.gen_btn = PrimaryPushButton("Generate", self)
        self.gen_btn.clicked.connect(self._on_generate)
        row.addWidget(self.gen_btn)

        self.iter_btn = PushButton("Iterate", self)
        self.iter_btn.setToolTip("Modify the current model with the new prompt")
        self.iter_btn.clicked.connect(self._on_iterate)
        self.iter_btn.setEnabled(False)
        row.addWidget(self.iter_btn)

        self.stop_btn = PushButton("Stop", self)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        row.addWidget(self.stop_btn)

        root.addLayout(row)

        if not _HAS_BUILD123D:
            warn = CaptionLabel(
                "⚠ build123d non disponible — nécessite Python <3.13. "
                "Créez un environnement Python 3.12 : "
                "conda create -n ada python=3.12 && pip install build123d",
                self
            )
            warn.setStyleSheet("color: #f0883e; padding: 4px 0;")
            root.addWidget(warn)
            self.gen_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)

        self.status_label = CaptionLabel("Status: Idle" if _HAS_BUILD123D else "Status: build123d manquant", self)
        root.addWidget(self.status_label)

        # Splitter: log left, viewer right
        splitter = QSplitter(Qt.Horizontal, self)

        # Log panel
        log_card = CardWidget(self)
        log_layout = QVBoxLayout(log_card)
        log_layout.addWidget(StrongBodyLabel("Generation Log", self))
        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 10))
        self.log_view.setStyleSheet("background: #0d1117; color: #c9d1d9; border: none;")
        log_layout.addWidget(self.log_view)

        # File action row
        file_row = QHBoxLayout()
        self.open_btn = PushButton("Open STL", self)
        self.open_btn.clicked.connect(self._open_stl)
        self.open_btn.setEnabled(False)
        self.open_folder_btn = PushButton("Open Folder", self)
        self.open_folder_btn.clicked.connect(self._open_folder)
        file_row.addWidget(self.open_btn)
        file_row.addWidget(self.open_folder_btn)
        file_row.addStretch()
        log_layout.addLayout(file_row)

        splitter.addWidget(log_card)

        # 3D viewer panel
        viewer_card = CardWidget(self)
        viewer_layout = QVBoxLayout(viewer_card)
        viewer_layout.setContentsMargins(0, 4, 0, 0)
        viewer_layout.addWidget(StrongBodyLabel("3D Preview", self))

        if _HAS_WEBENGINE:
            self.viewer = QWebEngineView(self)
            settings = self.viewer.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            self.viewer.setHtml(_VIEWER_HTML)
            viewer_layout.addWidget(self.viewer)
        else:
            self.viewer = None
            no_viewer = CaptionLabel(
                "Install PySide6-WebEngine for 3D preview.\n"
                "STL files are saved to ~/ADA_CAD/", self
            )
            no_viewer.setAlignment(Qt.AlignCenter)
            viewer_layout.addWidget(no_viewer)

        splitter.addWidget(viewer_card)
        splitter.setSizes([380, 500])
        root.addWidget(splitter, stretch=1)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_generate(self):
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return
        self._start_agent(prompt, iterate=False)

    def _on_iterate(self):
        prompt = self.prompt_input.text().strip()
        if not prompt or not self._current_code:
            return
        self._start_agent(prompt, iterate=True)

    def _on_stop(self):
        if self._agent:
            self._agent.stop()
        self.status_label.setText("Status: Stopping…")
        self.stop_btn.setEnabled(False)

    def _open_stl(self):
        if self._current_stl and os.path.exists(self._current_stl):
            import subprocess as sp, sys
            if sys.platform == "win32":
                os.startfile(self._current_stl)
            else:
                sp.Popen(["xdg-open", self._current_stl])

    def _open_folder(self):
        import subprocess as sp, sys
        folder = str(OUTPUT_DIR)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            sp.Popen(["xdg-open", folder])

    # ── Agent lifecycle ───────────────────────────────────────────────────────

    def _start_agent(self, prompt: str, iterate: bool):
        self.log_view.clear()
        self.status_label.setText("Status: Running…")
        self.gen_btn.setEnabled(False)
        self.iter_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_btn.setEnabled(False)
        self._log(f"{'Iterating' if iterate else 'Generating'}: {prompt}")

        self._agent = CadAgent()
        self._agent.log.connect(self._log)
        self._agent.thinking.connect(self._on_thinking)
        self._agent.finished.connect(self._on_finished)

        current = self._current_code if iterate else ""
        self._worker = _WorkerThread(self._agent, prompt, current, self)
        self._agent.moveToThread(self._worker)
        self._worker.start()

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(str)
    def _log(self, text: str):
        self.log_view.append(text)

    @Slot(str)
    def _on_thinking(self, text: str):
        # Show thinking inline but truncated to avoid flooding the log
        if len(text) > 120:
            text = text[:120] + "…"
        self.log_view.append(f"  <think> {text}")

    @Slot(dict)
    def _on_finished(self, result: dict):
        self.gen_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if result["success"]:
            stl_path = result["stl_path"]
            self._current_stl = stl_path
            self._current_code = result["code"]
            self.status_label.setText(f"Status: Done — {Path(stl_path).name}")
            self._log(f"\n✓ STL saved: {stl_path}")
            self.open_btn.setEnabled(True)
            self.iter_btn.setEnabled(True)
            self._load_stl_preview(stl_path)
        else:
            self.status_label.setText(f"Status: Failed")
            self._log(f"\n✗ {result.get('error', 'Unknown error')}")

        if self._worker:
            self._worker.quit()
            self._worker.wait(3000)

    def _load_stl_preview(self, stl_path: str):
        if not self.viewer or not _HAS_WEBENGINE:
            return
        try:
            from core.agent.cad_agent import CadAgent
            b64 = CadAgent.read_stl_b64(stl_path)
            name = Path(stl_path).name
            js = f"loadSTLData('{b64}', '{name}');"
            self.viewer.page().runJavaScript(js)
        except Exception as e:
            self._log(f"  Preview error: {e}")

    def closeEvent(self, event):
        self._on_stop()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        super().closeEvent(event)

    # ── External API (called from handlers.py) ────────────────────────────────

    def start_generation(self, prompt: str):
        """Trigger generation from outside (e.g., chat routing)."""
        self.prompt_input.setText(prompt)
        self._on_generate()
