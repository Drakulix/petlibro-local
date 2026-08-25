// ── Help / About ──────────────────────────────────────────────────────────
async function openAbout() {
  document.getElementById("modal-about").classList.add("open");
  try {
    const info = await api("GET", "/api/about");
    document.getElementById("about-version").textContent = info.version || "—";
    document.getElementById("about-ha-version").textContent = info.ha_version || "—";
  } catch {
    document.getElementById("about-version").textContent = "—";
    document.getElementById("about-ha-version").textContent = "—";
  }
}

async function downloadDebugCapture() {
  const btn = document.getElementById("btn-debug-capture");
  const originalText = btn.textContent;
  btn.disabled = true;
  try {
    const r = await fetch(`${BASE}/api/diag/debug-capture`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const blob = await r.blob();
    const disposition = r.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : "petlibro-debug-capture.log";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch(e) {
    alert(t("about.debug_capture_failed", {error: e.message}));
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// ── Settings ──────────────────────────────────────────────────────────────
function renderSettings() {
  document.getElementById("s-mqtt-host").value = _settings.mqtt_host || "";
  document.getElementById("s-mqtt-port").value = _settings.mqtt_port || 1883;
  document.getElementById("s-mqtt-user").value = _settings.mqtt_user || "";
  document.getElementById("s-mqtt-pass").value = _settings.mqtt_pass || "";
  const unitsSel = document.getElementById("s-units");
  if (unitsSel) {
    for (const opt of unitsSel.options) {
      if (opt.value === (_settings.units || "auto")) { opt.selected = true; break; }
    }
  }
  const bellCb = document.getElementById("s-notify-bell");
  if (bellCb) bellCb.checked = _settings.notify_bell_enabled !== false;

  const emailTo = document.getElementById("s-notify-email-to");
  if (emailTo) emailTo.value = _settings.notify_email_to || "";

  _populateNotifyDropdowns();

  const langSel = document.getElementById("s-language");
  if (_settings.language) {
    for (const opt of langSel.options) {
      if (opt.value === _settings.language) { opt.selected = true; break; }
    }
  }
  const tzSel = document.getElementById("s-feeder-tz");
  if (tzSel) {
    const tzVal = _settings.feeder_timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
    for (const opt of tzSel.options) {
      if (opt.value === tzVal) { opt.selected = true; break; }
    }
  }
}


async function saveSettings(fromTab) {
  const body = {
    mqtt_host: document.getElementById("s-mqtt-host").value.trim(),
    mqtt_port: parseInt(document.getElementById("s-mqtt-port").value) || 1883,
    mqtt_user: document.getElementById("s-mqtt-user").value.trim(),
    mqtt_pass: document.getElementById("s-mqtt-pass").value,
    language: document.getElementById("s-language").value,
    units: document.getElementById("s-units").value,
    feeder_timezone: document.getElementById("s-feeder-tz")?.value || "America/Denver",
    notify_bell_enabled: document.getElementById("s-notify-bell")?.checked !== false,
    notify_email_service: document.getElementById("s-notify-email-service")?.value || "",
    notify_email_to: (document.getElementById("s-notify-email-to")?.value || "").trim(),
    notify_mobile_default_service: document.getElementById("s-notify-mobile-service")?.value || "",
  };
  const statusEl = document.getElementById("mqtt-status");
  statusEl.className = "mqtt-status";
  try {
    const result = await api("POST", "/api/settings", body);
    _settings = result;
    const ind = document.getElementById(`save-indicator-${fromTab}`);
    if (ind) { ind.classList.add("show"); setTimeout(() => ind.classList.remove("show"), 2000); }
    if (result.mqtt_ok === true) {
      statusEl.className = "mqtt-status ok";
      statusEl.textContent = t("settings.mqtt_ok");
      document.getElementById("setup-banner").classList.remove("show");
    } else if (result.mqtt_ok === false) {
      statusEl.className = "mqtt-status fail";
      statusEl.textContent = t("settings.mqtt_fail");
    }
    // Refresh device render since units may have changed
    _lastDeviceRenderKey = "";
    renderDevices();
  } catch(e) { alert(t("settings.save_failed", {error: e.message})); }
}

async function loadLanguages() {
  try {
    const langs = await api("GET", "/locales/available");
    const sel = document.getElementById("s-language");
    sel.innerHTML = langs.map(l => `<option value="${escHtml(l)}">${l.toUpperCase()}</option>`).join("");
  } catch {}
}

// ── MQTT setup check ──────────────────────────────────────────────────────
function isMqttConfigured() {
  return !!((_settings.mqtt_user || "").trim() && (_settings.mqtt_host || "").trim());
}

function checkMqttSetup() {
  const banner = document.getElementById("setup-banner");
  if (!isMqttConfigured()) {
    banner.classList.add("show");
    switchTab("settings");
    switchSettingsTab("mqtt");
  } else {
    banner.classList.remove("show");
  }
}

function checkPetSetup() {
  const banner = document.getElementById("pet-setup-banner");
  if (!banner) return;
  if (!isMqttConfigured() || !_devices.length || _pets.length > 0) {
    banner.style.display = "none";
    return;
  }
  banner.style.display = "";
}

// ── Crop modal ────────────────────────────────────────────────────────────
let _cropState = null;
let _cropCallback = null;

function openCropModal(file, onCrop) {
  _cropCallback = onCrop;
  const reader = new FileReader();
  reader.onload = e => {
    const img = new Image();
    img.onload = () => {
      const SIZE = 280;
      const minScale = Math.max(SIZE / img.width, SIZE / img.height);
      _cropState = {
        img,
        scale: minScale,
        minScale,
        ox: 0, oy: 0,
        dragging: false, lastX: 0, lastY: 0,
      };
      document.getElementById("crop-zoom").min = minScale;
      document.getElementById("crop-zoom").max = minScale * 6;
      document.getElementById("crop-zoom").step = minScale * 0.005;
      document.getElementById("crop-zoom").value = minScale;
      _cropDraw();
      document.getElementById("modal-crop").classList.add("open");
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function _cropDraw() {
  const canvas = document.getElementById("crop-canvas");
  const ctx = canvas.getContext("2d");
  const SIZE = 280;
  const { img, scale, ox, oy } = _cropState;
  const w = img.width * scale;
  const h = img.height * scale;
  const x = (SIZE - w) / 2 + ox;
  const y = (SIZE - h) / 2 + oy;
  ctx.clearRect(0, 0, SIZE, SIZE);
  ctx.drawImage(img, x, y, w, h);
}

function _cropClamp() {
  const SIZE = 280;
  const { img, scale } = _cropState;
  const w = img.width * scale;
  const h = img.height * scale;
  const maxOx = Math.max(0, (w - SIZE) / 2);
  const maxOy = Math.max(0, (h - SIZE) / 2);
  _cropState.ox = Math.max(-maxOx, Math.min(maxOx, _cropState.ox));
  _cropState.oy = Math.max(-maxOy, Math.min(maxOy, _cropState.oy));
}

function _applyCrop() {
  const SIZE = 280;
  const EXPORT = 400;
  const ratio = EXPORT / SIZE;
  const offCanvas = document.createElement("canvas");
  offCanvas.width = EXPORT; offCanvas.height = EXPORT;
  const ctx = offCanvas.getContext("2d");
  // Circular clip
  ctx.beginPath();
  ctx.arc(EXPORT / 2, EXPORT / 2, EXPORT / 2, 0, Math.PI * 2);
  ctx.clip();
  const { img, scale, ox, oy } = _cropState;
  const w = img.width * scale * ratio;
  const h = img.height * scale * ratio;
  const x = (EXPORT - w) / 2 + ox * ratio;
  const y = (EXPORT - h) / 2 + oy * ratio;
  ctx.drawImage(img, x, y, w, h);
  offCanvas.toBlob(blob => {
    document.getElementById("modal-crop").classList.remove("open");
    if (_cropCallback) _cropCallback(blob);
  }, "image/png");
}

function _wireCropModal() {
  const wrap = document.getElementById("crop-canvas-wrap");
  const canvas = document.getElementById("crop-canvas");

  // Mouse drag
  wrap.addEventListener("mousedown", e => {
    if (!_cropState) return;
    _cropState.dragging = true;
    _cropState.lastX = e.clientX;
    _cropState.lastY = e.clientY;
  });
  window.addEventListener("mousemove", e => {
    if (!_cropState?.dragging) return;
    _cropState.ox += e.clientX - _cropState.lastX;
    _cropState.oy += e.clientY - _cropState.lastY;
    _cropState.lastX = e.clientX;
    _cropState.lastY = e.clientY;
    _cropClamp();
    _cropDraw();
  });
  window.addEventListener("mouseup", () => { if (_cropState) _cropState.dragging = false; });

  // Touch drag
  let _lastTouchX = 0, _lastTouchY = 0;
  wrap.addEventListener("touchstart", e => {
    if (!_cropState || e.touches.length !== 1) return;
    _lastTouchX = e.touches[0].clientX;
    _lastTouchY = e.touches[0].clientY;
    e.preventDefault();
  }, { passive: false });
  wrap.addEventListener("touchmove", e => {
    if (!_cropState || e.touches.length !== 1) return;
    _cropState.ox += e.touches[0].clientX - _lastTouchX;
    _cropState.oy += e.touches[0].clientY - _lastTouchY;
    _lastTouchX = e.touches[0].clientX;
    _lastTouchY = e.touches[0].clientY;
    _cropClamp();
    _cropDraw();
    e.preventDefault();
  }, { passive: false });

  // Zoom slider
  document.getElementById("crop-zoom").addEventListener("input", e => {
    if (!_cropState) return;
    _cropState.scale = parseFloat(e.target.value);
    _cropClamp();
    _cropDraw();
  });

  document.getElementById("btn-crop-apply").addEventListener("click", _applyCrop);
  document.getElementById("btn-crop-cancel").addEventListener("click", () => {
    document.getElementById("modal-crop").classList.remove("open");
  });
}
